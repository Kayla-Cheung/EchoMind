"""SQLite persistence with immutable trial snapshots and separate human reviews."""
import csv
import io
import json
import math
import sqlite3
import threading
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

from .design import initial_design, validate_design


class Store:
    def __init__(self, path):
        # A relative override is relative to this project, never the shell's cwd.
        candidate = Path(path).expanduser()
        self.path = (candidate if candidate.is_absolute() else Path(__file__).resolve().parents[1] / candidate).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trials (id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    batch_id TEXT, source TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS human_ground_truth (participant_id TEXT NOT NULL,
                    anxiety_score REAL NOT NULL, scenario_id TEXT NOT NULL,
                    interpretation TEXT NOT NULL, action TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state_human_datasets (id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    payload TEXT NOT NULL);
            """)
            if not db.execute("SELECT 1 FROM settings WHERE key='design'").fetchone():
                db.execute("INSERT INTO settings VALUES ('design',?)", (json.dumps(initial_design(), ensure_ascii=False),))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def design(self):
        with self.lock, self.connection() as db:
            return json.loads(db.execute("SELECT value FROM settings WHERE key='design'").fetchone()[0])

    def setting(self, key, default=None):
        with self.lock, self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def save_setting(self, key, value, *, immutable=False):
        with self.lock, self.connection() as db:
            if immutable and db.execute("SELECT 1 FROM settings WHERE key=?", (key,)).fetchone():
                raise ValueError("版本已存在；请使用新版本号")
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False, allow_nan=False)))

    def settings_prefix(self, prefix):
        with self.lock, self.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT value FROM settings WHERE substr(key,1,?)=? ORDER BY key", (len(prefix), prefix))]

    def backup(self, reason="before-import"):
        folder = self.path.parent / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = folder / f"{reason}-{name}-{uuid.uuid4().hex[:8]}.sqlite3"
        with self.lock, self.connection() as source, closing(sqlite3.connect(target)) as dest:
            source.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("备份完整性检查失败；未执行写入")
        return str(target)

    def save_design(self, design):
        validate_design(design)
        with self.lock, self.connection() as db:
            db.execute("UPDATE settings SET value=? WHERE key='design'", (json.dumps(design, ensure_ascii=False),))
        return design

    def add_trial(self, record):
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO trials VALUES (?,?,?,?,?,?)", (record["id"], record["timestamp"],
                record.get("batch_id"), record["source"], record["status"], json.dumps(record, ensure_ascii=False)))

    def ensure_acquisition_schema(self):
        """Lazy additive migration; old protocols never need to change their database."""
        with self.lock:
            with self.connection() as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='acquisition_snapshots'").fetchone():
                    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='acquisition_call_events'").fetchone():
                        raise ValueError("记忆获取数据库结构不完整；停止运行并检查备份")
                    return
            backup = self.backup("before-memory-acquisition-v02-schema")
            with self.connection() as db:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS acquisition_snapshots (
                        id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, payload TEXT NOT NULL,
                        payload_hash TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS acquisition_call_events (
                        id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, payload TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS acquisition_snapshot_batch ON acquisition_snapshots(batch_id);
                    CREATE INDEX IF NOT EXISTS acquisition_call_batch ON acquisition_call_events(batch_id);
                    CREATE TRIGGER IF NOT EXISTS acquisition_snapshot_no_update
                    BEFORE UPDATE ON acquisition_snapshots BEGIN SELECT RAISE(ABORT,'immutable memory snapshot'); END;
                    CREATE TRIGGER IF NOT EXISTS acquisition_snapshot_no_delete
                    BEFORE DELETE ON acquisition_snapshots BEGIN SELECT RAISE(ABORT,'immutable memory snapshot'); END;
                    CREATE TRIGGER IF NOT EXISTS acquisition_call_no_update
                    BEFORE UPDATE ON acquisition_call_events BEGIN SELECT RAISE(ABORT,'immutable call audit'); END;
                    CREATE TRIGGER IF NOT EXISTS acquisition_call_no_delete
                    BEFORE DELETE ON acquisition_call_events BEGIN SELECT RAISE(ABORT,'immutable call audit'); END;
                    COMMIT;
                """)
            self.save_setting("schema:memory_acquisition_v02", {"version": 1, "backup": backup,
                              "timestamp": datetime.now(timezone.utc).isoformat()}, immutable=True)

    def freeze_memory(self, snapshot):
        from .history import canonical, digest
        raw, hashed = canonical(snapshot), digest(snapshot)
        with self.lock, self.connection() as db:
            old = db.execute("SELECT payload,payload_hash FROM acquisition_snapshots WHERE id=?", (snapshot["id"],)).fetchone()
            if old:
                if old[0] != raw or old[1] != hashed:
                    raise ValueError("冻结快照不可覆盖")
                return hashed
            db.execute("INSERT INTO acquisition_snapshots VALUES (?,?,?,?)",
                       (snapshot["id"], snapshot["batch_id"], raw, hashed))
        return hashed

    def acquisition_rows(self, table, batch_id=None):
        if table not in ("acquisition_snapshots", "acquisition_call_events"):
            raise ValueError("未知审计表")
        with self.lock, self.connection() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                return []
            query = "SELECT payload FROM " + table
            return [json.loads(r[0]) for r in db.execute(query + (" WHERE batch_id=?" if batch_id else "") + " ORDER BY rowid",
                                                         (batch_id,) if batch_id else ())]

    def memory_snapshot(self, snapshot_id):
        from .history import digest
        with self.lock, self.connection() as db:
            row = db.execute("SELECT payload,payload_hash FROM acquisition_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if not row:
            raise ValueError("找不到冻结快照")
        value = json.loads(row[0])
        if digest(value) != row[1]:
            raise ValueError("冻结快照校验失败；禁止继续分支")
        return value

    def add_acquisition_call_event(self, event):
        from .history import canonical
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO acquisition_call_events VALUES (?,?,?)",
                       (event["id"], event["batch_id"], canonical(event)))

    def update_trial(self, record):
        with self.lock, self.connection() as db:
            db.execute("UPDATE trials SET status=?, payload=? WHERE id=?", (record["status"], json.dumps(record, ensure_ascii=False), record["id"]))

    def trials(self):
        with self.lock, self.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM trials ORDER BY created_at,id")]

    def review(self, trial_id, coding, reviewer_note):
        with self.lock, self.connection() as db:
            row = db.execute("SELECT payload FROM trials WHERE id=?", (trial_id,)).fetchone()
            if not row:
                raise ValueError("找不到试次")
            record = json.loads(row[0])
            record["human_review"] = {"coding": coding, "note": reviewer_note,
                "timestamp": datetime.now(timezone.utc).isoformat()}
            db.execute("UPDATE trials SET payload=? WHERE id=?", (json.dumps(record, ensure_ascii=False), trial_id))
            return record

    def import_human(self, csv_text):
        reader = csv.DictReader(io.StringIO(csv_text))
        fields = {"participant_id", "anxiety_score", "scenario_id", "interpretation", "action"}
        if not reader.fieldnames or not fields.issubset(reader.fieldnames):
            raise ValueError("CSV 缺少指定的五列")
        rows = []
        for r in reader:
            if not r["participant_id"] or not r["scenario_id"]:
                raise ValueError("参与者和情境 ID 不能为空")
            score = float(r["anxiety_score"])
            if not math.isfinite(score) or r["interpretation"] not in ("positive", "neutral", "negative", "unclear") or r["action"] not in ("approach", "wait", "avoid", "other"):
                raise ValueError("人类记录中的分数或编码无效")
            rows.append((r["participant_id"], score, r["scenario_id"], r["interpretation"], r["action"]))
        with self.lock, self.connection() as db:
            db.executemany("INSERT INTO human_ground_truth VALUES (?,?,?,?,?)", rows)
        return len(rows)

    def human_count(self):
        with self.lock, self.connection() as db:
            return db.execute("SELECT COUNT(*) FROM human_ground_truth").fetchone()[0]

    def state_protocol(self):
        from .state_protocol import default_protocol
        with self.lock, self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key='state_protocol'").fetchone()
        return json.loads(row[0]) if row else default_protocol(self.design())

    def save_state_protocol(self, config):
        from .state_protocol import validate_protocol
        validate_protocol(config, self.design())
        with self.lock, self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('state_protocol',?)", (json.dumps(config, ensure_ascii=False),))
        return config

    def state_benchmarks(self):
        with self.lock, self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM state_human_datasets ORDER BY created_at")]

    def import_state_benchmark(self, data):
        from .state_analysis import parse_benchmark
        from .state_protocol import fingerprint
        record = parse_benchmark(data, self.state_protocol())
        digest = fingerprint(record)
        for previous in self.state_benchmarks():
            if previous.get("content_hash") == digest:
                raise ValueError("此人类数据集已导入，未重复写入")
        record.update({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), "content_hash": digest})
        with self.lock, self.connection() as db:
            db.execute("INSERT INTO state_human_datasets VALUES (?,?,?)", (record["id"], record["created_at"], json.dumps(record, ensure_ascii=False)))
        return record
