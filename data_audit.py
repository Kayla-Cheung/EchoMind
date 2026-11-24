"""Independent evidence review server. Source SQLite connections are always read-only.

No experiment modules, environment loaders or provider clients are imported.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
import sqlite3
import threading
import uuid
from urllib.parse import parse_qs, urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'private_exports' / 'data-audit'

THREAT_RE = re.compile(
    r'(怀疑|排斥|针对|不喜欢|忽略|跳过|冷落|讨厌|嫌弃|刻意|故意|不重要|不想理|排挤|不被重视|疏远|敷衍|质疑|否定|看轻|边缘化|紧张|不安|担心|尴尬|害怕|戒备|防备|敌意|反感|不满意|拒绝|懷疑|針對|不喜歡|跳過|討厭|嫌棄|排擠|不被重視|疏遠|質疑|邊緣化|緊張|擔心|尷尬|敵意|拒絕)'
)
BENIGN_RE = re.compile(
    r'(可能|也许|或许|忙|只是|刚好|暂时|没注意|没看到|正常|巧合|未必|无意|太吵|没听见|手头|事情多|晚些|抽不出空|流程|安排|延迟|故障|预热|卡纸|排队|设备|也許|或許|剛好|暫時|沒注意|沒看到|無意|沒聽見|手頭|延遲|預熱|卡紙|排隊|設備)'
)
S4_SPILLOVER_RE = re.compile(
    r'(陈晨|许宁|讨论课|小组|发言|跳过|上次|昨天|半年前|之前|排斥|忽略|冷落|队友|同学|同事|大家|他们|针对|讨厌|不被重视|人际|社交|陳晨|許寧|討論課|小組|發言|跳過|隊友|同學|他們|針對|討厭|人際)'
)

CODING_AXES = (
    'threat_attribution',
    'benign_attribution',
    'memory_intrusion',
    'behavioral_avoidance',
)

STATIC_FILES = {
    '/': ('web/data-audit.html', 'text/html; charset=utf-8'),
    '/data-audit.css': ('web/data-audit.css', 'text/css; charset=utf-8'),
    '/data-audit.js': ('web/data-audit.js', 'text/javascript; charset=utf-8'),
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    ).hexdigest()


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    return db


def decoded(row):
    value = dict(row)
    if 'payload' in value:
        value['payload'] = json.loads(value['payload'])
    return value


def _safe_json(value):
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def _ordinal_w1(dist_a, dist_b):
    if len(dist_a) != 4 or len(dist_b) != 4:
        return None
    if abs(sum(dist_a) - 1.0) > 1e-6 or abs(sum(dist_b) - 1.0) > 1e-6:
        return None
    return sum(abs(sum(dist_a[:k]) - sum(dist_b[:k])) for k in (1, 2, 3))


def extract_trial_fields(record):
    """Extract readable interpretation/speech/action/narrative and scenario prompt from a trial payload."""
    if not isinstance(record, dict):
        return {'interpretation': '', 'speech': '', 'action': '', 'narrative': '', 'scenario_title': '', 'scenario_prompt': ''}
    narrative = str(record.get('narrative') or '')
    parsed = record.get('agent_parsed') if isinstance(record.get('agent_parsed'), dict) else None
    channels = record.get('channels') if isinstance(record.get('channels'), dict) else None
    interp = speech = action = ''
    if parsed:
        interp = str(parsed.get('interpretation') or '')
        speech = str(parsed.get('speech') or '')
        action = str(parsed.get('action') or '')
    elif channels:
        interp = str(channels.get('thought') or channels.get('interpretation') or '')
        speech = str(channels.get('speech') or '')
        action = str(channels.get('behavior') or channels.get('action') or '')
    elif narrative.strip().startswith('{'):
        maybe = _safe_json(narrative)
        if isinstance(maybe, dict):
            interp = str(maybe.get('interpretation') or maybe.get('thought') or '')
            speech = str(maybe.get('speech') or '')
            action = str(maybe.get('action') or maybe.get('behavior') or '')

    sid = str(record.get('scenario_id') or '')
    scen_title, scen_prompt = sid, ''
    scen = record.get('scenario')
    if isinstance(scen, dict):
        scen_title = str(scen.get('title') or scen.get('name') or sid)
        scen_prompt = str(scen.get('prompt') or scen.get('text') or scen.get('description') or '')
    else:
        snap = record.get('snapshot')
        if isinstance(snap, dict):
            for key in ('scenarios', 'design'):
                sub = snap.get(key)
                items = sub if isinstance(sub, list) else (sub.get('scenarios') if isinstance(sub, dict) else None)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and item.get('id') == sid:
                            scen_title = str(item.get('title') or item.get('name') or sid)
                            scen_prompt = str(item.get('prompt') or item.get('text') or item.get('description') or '')
                            break
                    if scen_prompt:
                        break
        if not scen_prompt and isinstance(record.get('role_messages'), list):
            for msg in reversed(record['role_messages']):
                if isinstance(msg, dict) and msg.get('role') == 'user':
                    scen_prompt = str(msg.get('content') or '')[:600]
                    break

    return {
        'interpretation': interp,
        'speech': speech,
        'action': action,
        'narrative': narrative,
        'scenario_title': scen_title,
        'scenario_prompt': scen_prompt,
    }


def trial_quality_flags(record):
    """Heuristic audit flags for open-ended trial records (diagnostic only, never modifies source)."""
    if not isinstance(record, dict):
        return []
    flags = []
    source = str(record.get('source') or '')
    status = str(record.get('status') or '')
    if source == 'MOCK_NOT_LLM':
        flags.append('mock_record')
    if status != 'complete' or record.get('error'):
        flags.append('error_record')
    fields = extract_trial_fields(record)
    combined = ' '.join(v for v in (fields['interpretation'], fields['speech'], fields['action'], fields['narrative']) if v).strip()
    if status == 'complete' and not combined:
        flags.append('missing_text')

    req_model = str(record.get('model') or record.get('model_id') or '')
    role_meta = record.get('role_meta') if isinstance(record.get('role_meta'), dict) else {}
    coder_meta = record.get('coder_meta') if isinstance(record.get('coder_meta'), dict) else {}
    ret_model = str(role_meta.get('response_model') or '')
    coder_model = str(record.get('evaluator_model') or record.get('coding_model') or coder_meta.get('response_model') or '')
    if source == 'LIVE_LLM_API' and ret_model and req_model and ret_model != req_model:
        flags.append('model_mismatch')
    if source == 'LIVE_LLM_API' and coder_model and req_model and coder_model != req_model:
        flags.append('cross_model_coder')

    mc = record.get('machine_coding') if isinstance(record.get('machine_coding'), dict) else {}
    conf = mc.get('coding_confidence')
    if source == 'LIVE_LLM_API' and status == 'complete' and conf is not None:
        try:
            if float(conf) < 0.7:
                flags.append('low_confidence')
        except (ValueError, TypeError):
            pass

    if source == 'LIVE_LLM_API' and status == 'complete':
        interp_text = fields['interpretation'] or fields['narrative']
        if mc.get('interpretation') == 'neutral' and THREAT_RE.search(interp_text) and BENIGN_RE.search(interp_text):
            flags.append('mixed_neutral_risk')
        if record.get('scenario_id') == 'S4_control' or record.get('scenario_kind') == 'control':
            if S4_SPILLOVER_RE.search(combined):
                flags.append('s4_memory_spillover')

    return flags


def _is_canonical_primary(rel_path):
    """Distinguish primary non-mirrored DBs from historical copies nested inside v03/v04 folders."""
    norm = rel_path.replace('\\', '/')
    if '/backups/' in f'/{norm}/' or norm.startswith('backups/'):
        return False
    if norm.startswith('experiments/v03-prompt-framing/data/') and not norm.endswith('prompt-framing-v03.sqlite3'):
        return False
    if norm.startswith('experiments/v04-temporal-context/data/') and not norm.endswith('temporal-context-v04.sqlite3'):
        return False
    if norm.endswith('http-verify.sqlite3') or norm.endswith('mimo-before-real.sqlite3'):
        return False
    return True


def inspect_database(path, base):
    rel_path = str(path.relative_to(base))
    info = {
        'path': rel_path,
        'tables': [],
        'issues': [],
        'groups': [],
        'quality_hints': Counter(),
        'has_rr': False,
        'is_primary_source': _is_canonical_primary(rel_path),
    }
    trials = []
    with closing(readonly(path)) as db:
        info['integrity'] = [r[0] for r in db.execute('PRAGMA integrity_check')]
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for name in tables:
            cols = [r[1] for r in db.execute('PRAGMA table_info(' + quote(name) + ')')]
            info['tables'].append({'name': name, 'n': db.execute('SELECT count(*) FROM ' + quote(name)).fetchone()[0], 'columns': cols})
        if 'trials' in tables:
            grouped = defaultdict(Counter)
            for row in db.execute('SELECT rowid AS _rowid_, * FROM trials'):
                try:
                    r = json.loads(row['payload'])
                    if not isinstance(r, dict):
                        raise ValueError('payload is not an object')
                    key = tuple(
                        str(r.get(k) or 'unknown')
                        for k in ('batch_id', 'protocol', 'source', 'phase', 'model', 'prompt_version', 'coder_version', 'protocol_hash')
                    )
                    grouped[key][r.get('status', 'unknown')] += 1
                    flags = []
                    for k in ('id', 'batch_id', 'source', 'status'):
                        if row[k] != r.get(k):
                            flags.append('column_payload_mismatch:' + k)
                    if not r.get('protocol'):
                        flags.append('protocol_missing')
                    if r.get('status') == 'complete' and not r.get('narrative'):
                        flags.append('response_missing')
                    if r.get('status') == 'complete' and not isinstance(r.get('machine_coding'), dict):
                        flags.append('coding_missing')
                    snap = r.get('memory_snapshot')
                    if snap and r.get('memory_snapshot_hash') and digest(snap) != r['memory_snapshot_hash']:
                        flags.append('memory_hash_mismatch')
                    if flags:
                        info['issues'].append({'table': 'trials', 'rowid': row['_rowid_'], 'id': r.get('id'), 'flags': flags})
                    for qf in trial_quality_flags(r):
                        info['quality_hints'][qf] += 1
                    trials.append({
                        'id': r.get('id'), 'hash': digest(r), 'rowid': row['_rowid_'],
                        'source': r.get('source'), 'status': r.get('status'), 'batch_id': r.get('batch_id'),
                        'snapshot_id': r.get('memory_snapshot_id'),
                    })
                except (ValueError, TypeError) as exc:
                    info['issues'].append({'table': 'trials', 'rowid': row['_rowid_'], 'flags': ['invalid_payload: ' + str(exc)]})
            fields = ('batch_id', 'protocol', 'source', 'phase', 'model', 'prompt_version', 'coder_version', 'protocol_hash')
            info['groups'] = [{**dict(zip(fields, k)), 'statuses': dict(v), 'n': sum(v.values())} for k, v in grouped.items()]
        if 'acquisition_snapshots' in tables:
            for r in db.execute('SELECT rowid AS _rowid_, * FROM acquisition_snapshots'):
                try:
                    if digest(json.loads(r['payload'])) == r['payload_hash']:
                        continue
                    flag = 'snapshot_hash_mismatch'
                except (ValueError, TypeError):
                    flag = 'invalid_snapshot_payload'
                info['issues'].append({'table': 'acquisition_snapshots', 'rowid': r['_rowid_'], 'flags': [flag]})
        if 'acquisition_call_events' in tables and 'trials' in tables:
            ids = {r['id'] for r in trials}
            orphan = set()
            for r in db.execute('SELECT payload FROM acquisition_call_events'):
                try:
                    v = json.loads(r[0])
                    tid = v.get('trial_id')
                    if tid and tid not in ids:
                        orphan.add(tid)
                except (ValueError, AttributeError):
                    info['issues'].append({'table': 'acquisition_call_events', 'flags': ['invalid_event_payload']})
            info['event_trial_ids_absent'] = len(orphan)
        if 'ratings' in tables:
            info['has_rr'] = 'episodes' in tables
            info['rating_counts'] = {str(r[0]): r[1] for r in db.execute('SELECT rating,count(*) FROM ratings GROUP BY rating')}
            info['invalid_ratings'] = db.execute("SELECT count(*) FROM ratings WHERE rating IS NULL OR typeof(rating)!='integer' OR rating NOT BETWEEN 1 AND 4").fetchone()[0]
            info['measurement'] = 'RR ordinal similarity 1–4; not emotion intensity'
        for name in ('episodes', 'batches', 'requests'):
            item = next((t for t in info['tables'] if t['name'] == name), None)
            if not item:
                continue
            state = next((k for k in ('status', 'state', 'parse_status') if k in item['columns']), None)
            if state:
                item['statuses'] = {str(r[0]): r[1] for r in db.execute('SELECT ' + quote(state) + ',count(*) FROM ' + quote(name) + ' GROUP BY ' + quote(state))}
        if 'episodes' in tables and 'ratings' in tables:
            info['episode_rating_counts'] = [
                dict(r) for r in db.execute(
                    'SELECT e.episode_id, e.status, count(r.episode_id) AS ratings FROM episodes e LEFT JOIN ratings r ON e.episode_id=r.episode_id GROUP BY e.episode_id,e.status'
                )
            ]
    info['quality_hints'] = dict(info['quality_hints'])
    with path.open('rb') as source:
        hasher = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            hasher.update(chunk)
        info['file_sha256'] = hasher.hexdigest()
    info['wal_present'] = Path(str(path) + '-wal').exists()
    return info, trials


def _validate_coding(coding):
    if coding is None:
        return None
    if not isinstance(coding, dict):
        raise ValueError('coding must be an object')
    cleaned = {}
    for axis in CODING_AXES:
        val = coding.get(axis)
        if val is None or val == '':
            cleaned[axis] = None
        elif isinstance(val, bool) or not isinstance(val, int) or val not in (0, 1, 2):
            raise ValueError(f'{axis} must be null or integer 0/1/2')
        else:
            cleaned[axis] = val
    cleaned['mixed_attribution'] = bool(coding.get('mixed_attribution'))
    # Honestly label workbench coding as unblinded unless produced via separate blind-packet workflow
    cleaned['coding_mode'] = 'unblinded_review'
    return cleaned


class Audit:
    def __init__(self, base, output=OUTPUT):
        self.base, self.output = Path(base).resolve(), Path(output).resolve()
        self.paths = {}
        self.report = None
        self._scan_lock = threading.Lock()

    def scan(self):
        with self._scan_lock:
            databases, variants, paths = [], defaultdict(lambda: defaultdict(list)), {}
            candidates = sorted(set(self.base.rglob('*.sqlite3')) | set(self.base.rglob('*.db')))
            for path in candidates:
                path = path.resolve()
                if not path.is_relative_to(self.base) or path.is_relative_to(self.output):
                    continue
                key = hashlib.sha256(str(path).encode()).hexdigest()[:20]
                paths[key] = path
                try:
                    info, trials = inspect_database(path, self.base)
                    info['key'] = key
                    info['role'] = (
                        'derived_recovery' if 'derived' in path.parts
                        else 'backup' if 'backups' in path.parts
                        else 'source'
                    )
                    for trial in ([] if info['role'] == 'derived_recovery' else trials):
                        variants[trial['id']][trial['hash']].append({'db': key, **trial})
                except (sqlite3.Error, ValueError, OSError) as exc:
                    info = {'key': key, 'path': str(path.relative_to(self.base)), 'error': str(exc), 'tables': [], 'groups': [], 'issues': [], 'quality_hints': {}}
                databases.append(info)
            conflicts = [{'id': i, 'variants': [{'hash': h, 'locations': v} for h, v in hs.items()]} for i, hs in variants.items() if len(hs) > 1]
            unique = [next(iter(hs.values()))[0] for hs in variants.values() if len(hs) == 1]
            now = datetime.now(timezone.utc)
            inventory_id = now.strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8]
            report = {
                'inventory_id': inventory_id, 'created_at': now.isoformat(), 'base': str(self.base),
                'databases': databases, 'unique_trial_ids': len(variants), 'conflicts': conflicts,
                'identical_extra_copies': sum(len(v) - 1 for hs in variants.values() for v in hs.values()),
                'unconflicted_trial_statuses': dict(Counter(str((r['source'], r['status'])) for r in unique)),
                'limits': [
                    'Database inventory is not a pooled sample. Duplicate IDs with different payloads require review.',
                    'Observed counts do not prove planned coverage. Check frozen config and job records.',
                    'Ratings share episodes/items; snapshot branches are dependent. Repeats are not human participants.',
                    'Human held-out results have already been inspected; reserve new untouched data for confirmation.',
                    'Scan uses one read transaction per database. File hash is a file fingerprint, not a WAL snapshot hash.',
                ],
            }
            self.paths, self.report = paths, report
            self.output.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(report, ensure_ascii=False, indent=2)
            (self.output / ('inventory-' + inventory_id + '.json')).write_text(serialized, encoding='utf-8')
            (self.output / 'inventory.json').write_text(serialized, encoding='utf-8')
            return report

    def latest_reviews_map(self):
        """Return latest append-only review per (db, table, str(rowid))."""
        if not (self.output / 'reviews.sqlite3').exists():
            return {}
        latest = {}
        with closing(self.reviews()) as db:
            for (raw,) in db.execute('SELECT payload FROM reviews ORDER BY id'):
                ev = json.loads(raw)
                latest[(ev['db'], ev['table'], str(ev['rowid']))] = ev
        return latest

    def _issue_rowids(self, key, table):
        if not self.report:
            return set()
        db_info = next((d for d in self.report.get('databases', []) if d.get('key') == key), None)
        if not db_info:
            return set()
        return {int(x['rowid']) for x in db_info.get('issues', []) if x.get('table') == table and x.get('rowid') is not None}

    def rows(self, key, table, offset=0, query='', *, batch_id='', source='', status='', flag='', review_status='', limit=40):
        path = self.paths[key]
        offset = max(0, int(offset))
        limit = max(1, min(200, int(limit)))
        latest_map = self.latest_reviews_map()
        issue_rowids = self._issue_rowids(key, table)

        with closing(readonly(path)) as db:
            allowed = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in allowed:
                raise ValueError('Unknown table')
            cols = [r[1] for r in db.execute('PRAGMA table_info(' + quote(table) + ')')]
            where_parts, params = [], []
            if query:
                where_parts.append('(' + ' OR '.join('instr(lower(CAST(' + quote(c) + ' AS TEXT)), lower(?))>0' for c in cols) + ')')
                params.extend([query] * len(cols))
            if batch_id and 'batch_id' in cols:
                where_parts.append(quote('batch_id') + '=?')
                params.append(batch_id)
            if source and 'source' in cols:
                where_parts.append(quote('source') + '=?')
                params.append(source)
            if status and 'status' in cols:
                where_parts.append(quote('status') + '=?')
                params.append(status)

            clause = (' WHERE ' + ' AND '.join(where_parts)) if where_parts else ''

            # If flag or review_status filter is requested, filter cleanly in Python after SQL pre-filter
            if flag or review_status:
                all_rows = [dict(r) for r in db.execute('SELECT rowid AS _audit_rowid_, * FROM ' + quote(table) + clause + ' ORDER BY rowid', params)]
                filtered = []
                for row in all_rows:
                    rid_str = str(row['_audit_rowid_'])
                    rev = latest_map.get((key, table, rid_str))
                    if review_status:
                        cur_dec = rev['decision'] if rev else 'unreviewed'
                        if review_status == 'coded':
                            c = (rev or {}).get('coding') or {}
                            if not all(c.get(ax) is not None for ax in CODING_AXES):
                                continue
                        elif cur_dec != review_status:
                            continue
                    if flag:
                        if flag == 'has_issue':
                            if row['_audit_rowid_'] not in issue_rowids:
                                continue
                        elif table == 'trials':
                            rec = _safe_json(row.get('payload'))
                            if flag not in trial_quality_flags(rec):
                                continue
                        else:
                            continue
                    filtered.append(row)
                total = len(filtered)
                page_rows = filtered[offset:offset + limit]
            else:
                total = db.execute('SELECT count(*) FROM ' + quote(table) + clause, params).fetchone()[0]
                page_rows = [
                    dict(r) for r in db.execute(
                        'SELECT rowid AS _audit_rowid_, * FROM ' + quote(table) + clause + ' ORDER BY rowid LIMIT ? OFFSET ?',
                        [*params, limit, offset],
                    )
                ]

        # Attach non-destructive preview metadata for UI readability (never alters raw row hashing via /api/row)
        enriched = []
        for row in page_rows:
            item = dict(row)
            rid_str = str(item['_audit_rowid_'])
            rev = latest_map.get((key, table, rid_str))
            item['_review_decision_'] = rev['decision'] if rev else 'unreviewed'
            coding = (rev or {}).get('coding') if isinstance(rev, dict) else None
            item['_review_coded_'] = bool(coding and all(coding.get(ax) is not None for ax in CODING_AXES))
            if table == 'trials' and isinstance(item.get('payload'), str):
                rec = _safe_json(item['payload'])
                if isinstance(rec, dict):
                    tf = extract_trial_fields(rec)
                    mc = rec.get('machine_coding') if isinstance(rec.get('machine_coding'), dict) else {}
                    item['_preview_'] = {
                        'protocol': rec.get('protocol') or 'unknown',
                        'model': rec.get('model') or '',
                        'condition': rec.get('condition') or rec.get('condition_id') or '',
                        'scenario_id': rec.get('scenario_id') or '',
                        'prompt_variant': rec.get('prompt_variant') or '',
                        'temporal_variant': rec.get('temporal_variant') or '',
                        'legacy_interpretation': mc.get('interpretation') or '',
                        'legacy_action': mc.get('action') or '',
                        'snippet': (tf['interpretation'] or tf['narrative'] or str(rec.get('error') or ''))[:180],
                        'flags': trial_quality_flags(rec),
                    }
            enriched.append(item)

        return {'total': total, 'rows': enriched}

    def row(self, key, table, rowid):
        with closing(readonly(self.paths[key])) as db:
            allowed = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in allowed:
                raise ValueError('Unknown table')
            r = db.execute('SELECT * FROM ' + quote(table) + ' WHERE rowid=?', (int(rowid),)).fetchone()
            if r is None:
                raise ValueError('Row no longer exists')
            return dict(r)

    def row_detail(self, key, table, rowid):
        """Return exact row + canonical row_hash + structured readable view (with RR linked data if applicable)."""
        raw_row = self.row(key, table, rowid)
        row_hash = digest(raw_row)
        view = {'kind': 'generic', 'table': table, 'rowid': int(rowid)}

        if table == 'trials' and isinstance(raw_row.get('payload'), str):
            rec = _safe_json(raw_row['payload'])
            if isinstance(rec, dict):
                tf = extract_trial_fields(rec)
                mc = rec.get('machine_coding') if isinstance(rec.get('machine_coding'), dict) else {}
                role_meta = rec.get('role_meta') if isinstance(rec.get('role_meta'), dict) else {}
                coder_meta = rec.get('coder_meta') if isinstance(rec.get('coder_meta'), dict) else {}
                view = {
                    'kind': 'trial',
                    'id': rec.get('id'),
                    'batch_id': rec.get('batch_id'),
                    'timestamp': rec.get('timestamp') or raw_row.get('created_at'),
                    'protocol': rec.get('protocol') or 'unknown',
                    'source': rec.get('source') or raw_row.get('source'),
                    'status': rec.get('status') or raw_row.get('status'),
                    'provider': rec.get('provider') or '',
                    'model': rec.get('model') or '',
                    'returned_model': role_meta.get('response_model') or '',
                    'coder_model': rec.get('evaluator_model') or rec.get('coding_model') or coder_meta.get('response_model') or '',
                    'condition': rec.get('condition') or rec.get('condition_id') or '',
                    'scenario_id': rec.get('scenario_id') or '',
                    'scenario_kind': rec.get('scenario_kind') or '',
                    'repeat': rec.get('repeat'),
                    'prompt_version': rec.get('prompt_version') or '',
                    'prompt_variant': rec.get('prompt_variant') or '',
                    'temporal_variant': rec.get('temporal_variant') or '',
                    'acquisition_method': rec.get('acquisition_method') or '',
                    'ablation_format': rec.get('ablation_format') or '',
                    'memory_source': rec.get('memory_source') or '',
                    'error': rec.get('error') or '',
                    **tf,
                    'machine_coding': mc,
                    'flags': trial_quality_flags(rec),
                    'role_messages': rec.get('role_messages'),
                    'evaluator_messages': rec.get('evaluator_messages'),
                    'evaluator_raw': rec.get('evaluator_raw'),
                    'memory_snapshot': rec.get('memory_snapshot'),
                }
        elif table == 'episodes' and raw_row.get('episode_id'):
            eid = raw_row['episode_id']
            with closing(readonly(self.paths[key])) as db:
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                reqs = [dict(r) for r in db.execute('SELECT * FROM requests WHERE episode_id=?', (eid,))] if 'requests' in tables else []
                rats = [dict(r) for r in db.execute('SELECT * FROM ratings WHERE episode_id=?', (eid,))] if 'ratings' in tables else []
            view = {
                'kind': 'rr_episode',
                'episode': {k: (_safe_json(v) if k.endswith('_json') else v) for k, v in raw_row.items()},
                'requests': [{k: (_safe_json(v) if k.endswith('_json') else v) for k, v in rq.items()} for rq in reqs],
                'ratings': rats,
            }

        return {'row': raw_row, 'hash': row_hash, 'view': view}

    def pairs(self, key, batch_id='', mode='auto'):
        """Build same-DB, same-batch paired view (SOP A4: explicit missing_side, never silently pools DBs)."""
        path = self.paths[key]
        latest_map = self.latest_reviews_map()
        rows_data = []
        with closing(readonly(path)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'trials' not in tables:
                raise ValueError('Selected database has no trials table')
            sql = 'SELECT rowid AS _rowid_, * FROM trials'
            params = []
            if batch_id:
                sql += ' WHERE batch_id=?'
                params.append(batch_id)
            sql += ' ORDER BY rowid'
            for r in db.execute(sql, params):
                rec = _safe_json(r['payload'])
                if not isinstance(rec, dict):
                    continue
                rows_data.append((int(r['_rowid_']), rec))

        if not rows_data:
            return {'db': key, 'batch_id': batch_id, 'mode': mode, 'pairs': [], 'unpaired': [], 'summary': {}}

        # Auto-select pairing axis within this batch
        if mode == 'auto':
            has_prompt_pair = any(rec.get('prompt_variant') in ('P0', 'P1') and rec.get('prompt_pair_id') for _, rec in rows_data)
            has_temp_pair = any(rec.get('temporal_variant') in ('T1', 'T2') for _, rec in rows_data)
            has_ablation = any(rec.get('ablation_format') in ('free', 'channels') for _, rec in rows_data)
            if has_temp_pair:
                mode = 'temporal'
            elif has_prompt_pair:
                mode = 'prompt'
            elif has_ablation:
                mode = 'ablation'
            else:
                mode = 'valence'

        def pack_side(rowid, rec):
            tf = extract_trial_fields(rec)
            mc = rec.get('machine_coding') if isinstance(rec.get('machine_coding'), dict) else {}
            rev = latest_map.get((key, 'trials', str(rowid)))
            return {
                'rowid': rowid,
                'id': rec.get('id'),
                'batch_id': rec.get('batch_id'),
                'source': rec.get('source'),
                'status': rec.get('status'),
                'condition': rec.get('condition') or rec.get('condition_id') or '',
                'scenario_id': rec.get('scenario_id') or '',
                'prompt_variant': rec.get('prompt_variant') or '',
                'temporal_variant': rec.get('temporal_variant') or '',
                'ablation_format': rec.get('ablation_format') or '',
                'interpretation': tf['interpretation'],
                'speech': tf['speech'],
                'action': tf['action'],
                'narrative': tf['narrative'],
                'legacy_interpretation': mc.get('interpretation') or '',
                'legacy_action': mc.get('action') or '',
                'flags': trial_quality_flags(rec),
                'review': rev,
            }

        grouped = defaultdict(dict)
        unpaired = []
        left_label, right_label, reason = 'Left', 'Right', ''

        if mode == 'prompt':
            left_label, right_label = 'P0', 'P1'
            reason = 'Same frozen memory_snapshot_id + scenario_id paired across P0/P1 prompt framing'
            for rowid, rec in rows_data:
                pv = rec.get('prompt_variant')
                pid = rec.get('prompt_pair_id') or f"{rec.get('batch_id')}:{rec.get('condition')}:{rec.get('scenario_id')}:{rec.get('repeat')}"
                if pv in ('P0', 'P1'):
                    grouped[(pid, rec.get('memory_snapshot_id') or rec.get('batch_id') or '')][pv] = pack_side(rowid, rec)
                else:
                    unpaired.append(pack_side(rowid, rec))
        elif mode == 'temporal':
            left_label, right_label = 'T1 (yesterday)', 'T2 (six months ago)'
            reason = 'Matched temporal_pair_id (condition x replicate x scenario) across T1/T2'
            for rowid, rec in rows_data:
                tv = rec.get('temporal_variant')
                pid = rec.get('temporal_pair_id') or rec.get('pair_id') or f"{rec.get('condition')}:{rec.get('scenario_id')}:{rec.get('repeat')}"
                if tv in ('T1', 'T2'):
                    grouped[(pid, f"{rec.get('condition')}:{rec.get('repeat')}")][tv] = pack_side(rowid, rec)
                else:
                    unpaired.append(pack_side(rowid, rec))
        elif mode == 'ablation':
            left_label, right_label = 'free', 'channels'
            reason = 'Same memory_source + condition + scenario_id + repeat across output format free/channels'
            for rowid, rec in rows_data:
                af = rec.get('ablation_format')
                pid = f"{rec.get('batch_id')}:{rec.get('memory_source')}:{rec.get('condition')}:{rec.get('scenario_id')}:r{rec.get('repeat')}"
                if af in ('free', 'channels'):
                    grouped[(pid, str(rec.get('batch_id') or ''))][af] = pack_side(rowid, rec)
                else:
                    unpaired.append(pack_side(rowid, rec))
        else:
            left_label, right_label = 'neutral', 'negative'
            reason = 'Same batch + acquisition_method + scenario_id + repeat across neutral/negative valence'
            for rowid, rec in rows_data:
                cond = str(rec.get('condition') or '')
                if cond.startswith('neutral_'):
                    method = cond[len('neutral_'):]
                    pid = f"{rec.get('batch_id')}:{method}:{rec.get('scenario_id')}:r{rec.get('repeat')}"
                    grouped[(pid, str(rec.get('batch_id') or ''))]['neutral'] = pack_side(rowid, rec)
                elif cond.startswith('negative_'):
                    method = cond[len('negative_'):]
                    pid = f"{rec.get('batch_id')}:{method}:{rec.get('scenario_id')}:r{rec.get('repeat')}"
                    grouped[(pid, str(rec.get('batch_id') or ''))]['negative'] = pack_side(rowid, rec)
                else:
                    unpaired.append(pack_side(rowid, rec))

        l_key = 'P0' if mode == 'prompt' else 'T1' if mode == 'temporal' else 'free' if mode == 'ablation' else 'neutral'
        r_key = 'P1' if mode == 'prompt' else 'T2' if mode == 'temporal' else 'channels' if mode == 'ablation' else 'negative'

        pairs_out = []
        left_leg, right_leg = Counter(), Counter()
        missing_count = 0
        changed_count = 0

        for (pid, block_id), sides in sorted(grouped.items()):
            left = sides.get(l_key)
            right = sides.get(r_key)
            missing_side = ''
            if left and not right:
                missing_side = r_key
                missing_count += 1
            elif right and not left:
                missing_side = l_key
                missing_count += 1
            if left:
                left_leg[left['legacy_interpretation'] or 'missing'] += 1
            if right:
                right_leg[right['legacy_interpretation'] or 'missing'] += 1
            changed = bool(left and right and left['legacy_interpretation'] != right['legacy_interpretation'])
            if changed:
                changed_count += 1
            ref = left or right
            pairs_out.append({
                'pair_id': pid,
                'block_id': block_id,
                'condition': ref['condition'] if ref else '',
                'scenario_id': ref['scenario_id'] if ref else '',
                'reason': reason,
                'missing_side': missing_side,
                'label_changed': changed,
                'left': left,
                'right': right,
            })

        return {
            'db': key,
            'path': str(path.relative_to(self.base)),
            'batch_id': batch_id,
            'mode': mode,
            'left_label': left_label,
            'right_label': right_label,
            'reason': reason,
            'summary': {
                'total_pairs': len(pairs_out),
                'complete_pairs': len(pairs_out) - missing_count,
                'missing_side_pairs': missing_count,
                'label_changed_pairs': changed_count,
                'unpaired_count': len(unpaired),
                'left_legacy_interpretation': dict(left_leg),
                'right_legacy_interpretation': dict(right_leg),
            },
            'pairs': pairs_out,
            'unpaired': unpaired,
        }

    def rr_summary(self, key):
        """Structured read-only RR audit summary for a single RR SQLite database."""
        path = self.paths[key]
        latest_map = self.latest_reviews_map()
        with closing(readonly(path)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'episodes' not in tables or 'ratings' not in tables:
                raise ValueError('Selected database is not an RR episodes/ratings database')

            batches = [dict(r) for r in db.execute('SELECT * FROM batches')] if 'batches' in tables else []
            meta = {r['key']: (_safe_json(r['value']) or r['value']) for r in db.execute('SELECT key, value FROM meta')} if 'meta' in tables else {}
            ep_rows = [dict(r) for r in db.execute('SELECT rowid AS _rowid_, * FROM episodes ORDER BY rowid')]
            req_rows = [dict(r) for r in db.execute('SELECT * FROM requests')] if 'requests' in tables else []
            rat_rows = [dict(r) for r in db.execute('SELECT * FROM ratings')]

            # Load human reference (table or sibling JSON)
            human_ref = {}
            if 'human_reference' in tables:
                for r in db.execute('SELECT * FROM human_reference'):
                    d = dict(r)
                    split = d.get('split') or d.get('split_name') or 'heldout'
                    col = d.get('human_column') or d.get('item_id') or ''
                    probs = _safe_json(d.get('distribution_json') or d.get('probabilities_json'))
                    if col and isinstance(probs, dict):
                        human_ref.setdefault(split, {})[col] = {
                            'n': d.get('n'),
                            'probabilities': {str(i): float(probs.get(str(i), 0.0)) for i in (1, 2, 3, 4)},
                        }
            else:
                sib_hr = path.parent / 'human_reference_aggregate.json'
                if sib_hr.exists():
                    parsed_hr = _safe_json(sib_hr.read_text(encoding='utf-8'))
                    if isinstance(parsed_hr, dict):
                        human_ref['heldout'] = parsed_hr

        # Optional sibling stimuli metadata for rr-isolation
        item_meta = {}
        sib_stim = path.parent.parent / 'private_inputs' / 'calm_rr_v42.json'
        if sib_stim.exists():
            stim = _safe_json(sib_stim.read_text(encoding='utf-8'))
            if isinstance(stim, dict):
                for s in stim.get('scenarios') or []:
                    for it in s.get('interpretations') or []:
                        item_meta[it.get('item_id')] = {
                            'scenario_id': s.get('id') or '',
                            'category': s.get('category') or '',
                            'rating_type': it.get('type') or '',
                        }

        ep_by_id = {e['episode_id']: e for e in ep_rows}
        req_by_ep = defaultdict(list)
        req_states = Counter()
        req_models = Counter()
        for rq in req_rows:
            st = rq.get('parse_status') or rq.get('state') or 'unknown'
            req_states[st] += 1
            req_models[rq.get('returned_model') or rq.get('requested_model') or 'unknown'] += 1
            req_by_ep[rq.get('episode_id')].append({
                'phase': rq.get('phase'),
                'state': st,
                'requested_model': rq.get('requested_model') or '',
                'returned_model': rq.get('returned_model') or '',
                'response_id': rq.get('response_id') or '',
                'latency_ms': rq.get('latency_ms'),
                'error': rq.get('error') or '',
            })

        rat_by_ep = defaultdict(list)
        grouped = defaultdict(list)
        for rt in rat_rows:
            eid = rt.get('episode_id')
            ep = ep_by_id.get(eid) or {}
            iid = rt.get('item_id') or ''
            im = item_meta.get(iid) or {}
            sid = rt.get('scenario_id') or im.get('scenario_id') or ep.get('scenario_id') or ''
            cat = rt.get('scenario_category') or rt.get('category') or im.get('category') or ''
            rtype = rt.get('rating_type') or rt.get('item_type') or im.get('rating_type') or ''
            cond = rt.get('condition_id') or ep.get('condition_id') or ''
            axis = ep.get('arm') or rt.get('prompt_variant') or ep.get('prompt_variant') or 'default'
            hcol = f'{sid}_{rtype}' if (sid and rtype) else ''
            entry = {
                'episode_id': eid, 'axis': axis, 'condition_id': cond,
                'scenario_id': sid, 'category': cat, 'item_id': iid,
                'rating_type': rtype, 'human_column': hcol, 'rating': rt.get('rating'),
            }
            rat_by_ep[eid].append(entry)
            grouped[(axis, cond, iid)].append(entry)

        ref_map = human_ref.get('heldout') or next(iter(human_ref.values()), {})
        w1_items = []
        for (axis, cond, iid), rows in sorted(grouped.items()):
            vals = [int(x['rating']) for x in rows if isinstance(x['rating'], int) and 1 <= x['rating'] <= 4]
            if not vals:
                continue
            sample = rows[0]
            ref = ref_map.get(sample['human_column'])
            n = len(vals)
            mean_v = sum(vals) / n
            var_v = sum((v - mean_v) ** 2 for v in vals) / n
            dist_w1 = None
            h_mean = None
            if ref and isinstance(ref.get('probabilities'), dict):
                m_dist = [vals.count(i) / n for i in (1, 2, 3, 4)]
                h_dist = [float(ref['probabilities'].get(str(i), 0.0)) for i in (1, 2, 3, 4)]
                dist_w1 = _ordinal_w1(m_dist, h_dist)
                h_mean = round(sum(i * h_dist[i - 1] for i in (1, 2, 3, 4)), 3)
            w1_items.append({
                'axis': axis, 'condition_id': cond, 'item_id': iid,
                'scenario_id': sample['scenario_id'], 'category': sample['category'],
                'rating_type': sample['rating_type'], 'n': n, 'ratings': vals,
                'model_mean': round(mean_v, 3), 'human_mean': h_mean,
                'variance': round(var_v, 4),
                'w1': round(dist_w1, 4) if dist_w1 is not None else None,
            })

        cell_groups = defaultdict(list)
        for item in w1_items:
            cell_groups[(item['axis'], item['condition_id'])].append(item)
        cell_summaries = []
        for (axis, cond), items in sorted(cell_groups.items()):
            all_w1 = [x['w1'] for x in items if x['w1'] is not None]
            soc_w1 = [x['w1'] for x in items if x['w1'] is not None and x['category'] == 'social']
            freq = Counter(v for x in items for v in x['ratings'])
            cell_summaries.append({
                'axis': axis, 'condition_id': cond, 'items': len(items),
                'all_w1_mean': round(sum(all_w1) / len(all_w1), 4) if all_w1 else None,
                'social_w1_mean': round(sum(soc_w1) / len(soc_w1), 4) if soc_w1 else None,
                'zero_variance_items': sum(1 for x in items if x['n'] > 1 and x['variance'] == 0),
                'freq': {str(i): freq.get(i, 0) for i in (1, 2, 3, 4)},
            })

        # Paired contrasts (P0 vs P1 or BATCH vs ISOLATED)
        axes = sorted({x['axis'] for x in w1_items})
        pair_spec = ('P0', 'P1', 'P1 - P0') if {'P0', 'P1'} <= set(axes) else ('BATCH', 'ISOLATED', 'ISOLATED - BATCH') if {'BATCH', 'ISOLATED'} <= set(axes) else None
        contrasts = []
        if pair_spec:
            a_arm, b_arm, delta_lbl = pair_spec
            idx = {(x['axis'], x['condition_id'], x['item_id']): x for x in w1_items}
            for cond in sorted({x['condition_id'] for x in w1_items}):
                d_all, d_soc, a_vals, b_vals = [], [], [], []
                for iid in sorted({x['item_id'] for x in w1_items if x['condition_id'] == cond}):
                    ia, ib = idx.get((a_arm, cond, iid)), idx.get((b_arm, cond, iid))
                    if ia and ib and ia['w1'] is not None and ib['w1'] is not None:
                        delta = ib['w1'] - ia['w1']
                        d_all.append(delta)
                        a_vals.append(ia['w1'])
                        b_vals.append(ib['w1'])
                        if ia['category'] == 'social':
                            d_soc.append(delta)
                if d_all:
                    contrasts.append({
                        'condition_id': cond, 'arm_a': a_arm, 'arm_b': b_arm, 'delta_label': delta_lbl,
                        'n_items': len(d_all),
                        'a_w1_mean': round(sum(a_vals) / len(a_vals), 4),
                        'b_w1_mean': round(sum(b_vals) / len(b_vals), 4),
                        'delta_all_mean': round(sum(d_all) / len(d_all), 4),
                        'delta_social_mean': round(sum(d_soc) / len(d_soc), 4) if d_soc else None,
                        'improved': sum(1 for d in d_all if d < 0),
                        'worsened': sum(1 for d in d_all if d > 0),
                        'tied': sum(1 for d in d_all if d == 0),
                    })

        episodes_out = []
        for ep in ep_rows:
            eid = ep['episode_id']
            rev = latest_map.get((key, 'episodes', str(ep['_rowid_'])))
            episodes_out.append({
                'rowid': ep['_rowid_'],
                'episode_id': eid,
                'batch_id': ep.get('batch_id') or 'RR-ISOLATION-001',
                'arm': ep.get('arm') or '',
                'prompt_variant': ep.get('prompt_variant') or '',
                'condition_id': ep.get('condition_id') or '',
                'scenario_id': ep.get('scenario_id') or 'ALL_9',
                'repeat_index': ep.get('repeat_index'),
                'status': ep.get('status') or '',
                'error': ep.get('error') or '',
                'ratings_count': len(rat_by_ep[eid]),
                'requests': req_by_ep[eid],
                'review_decision': rev['decision'] if rev else 'unreviewed',
            })

        return {
            'db': key,
            'path': str(path.relative_to(self.base)),
            'batches': batches,
            'meta': meta,
            'requests_summary': {'total': len(req_rows), 'by_state': dict(req_states), 'by_model': dict(req_models)},
            'ratings_count': len(rat_rows),
            'has_human_reference': bool(ref_map),
            'exploratory_notice': '已檢視的人類 held-out 分割僅作探索性對照，不可作為確認性驗收；W1 越小表示越接近人類參考分布。',
            'cell_summaries': cell_summaries,
            'contrasts': contrasts,
            'episodes': episodes_out,
        }

    def export_blind_packet(self, key, batch_id='', source='LIVE_LLM_API', seed='echomind-blind-v1'):
        """SOP A3: Export blinded coding CSV (no condition/model/machine_coding) and separate mapping JSON."""
        path = self.paths[key]
        rows = []
        with closing(readonly(path)) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'trials' not in tables:
                raise ValueError('Selected database has no trials table')
            where, params = [], []
            if batch_id:
                where.append('batch_id=?')
                params.append(batch_id)
            if source and source != 'ALL':
                where.append('source=?')
                params.append(source)
            clause = (' WHERE ' + ' AND '.join(where)) if where else ''
            for r in db.execute('SELECT rowid AS _rowid_, * FROM trials' + clause + ' ORDER BY rowid', params):
                raw_dict = {k: r[k] for k in r.keys() if k != '_rowid_'}
                rec = _safe_json(r['payload'])
                if not isinstance(rec, dict):
                    continue
                if rec.get('status') != 'complete':
                    continue
                rows.append((int(r['_rowid_']), raw_dict, rec))

        # Deterministic blind shuffle
        rows.sort(key=lambda item: hashlib.sha256(f'{seed}:{key}:{item[0]}:{item[2].get("id")}'.encode()).hexdigest())

        buf = io.StringIO()
        csv_fields = [
            'blind_order', 'blind_id', 'scenario_id', 'scenario_title', 'scenario_prompt',
            'interpretation', 'speech', 'action', 'narrative',
            'threat_attribution_0_2', 'benign_attribution_0_2', 'memory_intrusion_0_2',
            'behavioral_avoidance_0_2', 'mixed_attribution_0_1', 'coder_notes',
        ]
        writer = csv.DictWriter(buf, fieldnames=csv_fields)
        writer.writeheader()
        mapping = []

        for idx, (rowid, raw_dict, rec) in enumerate(rows, 1):
            bid = 'BLIND-' + hashlib.sha256(f'{seed}:{key}:{rowid}:{rec.get("id")}'.encode()).hexdigest()[:10].upper()
            tf = extract_trial_fields(rec)
            mc = rec.get('machine_coding') if isinstance(rec.get('machine_coding'), dict) else {}
            writer.writerow({
                'blind_order': idx,
                'blind_id': bid,
                'scenario_id': rec.get('scenario_id') or '',
                'scenario_title': tf['scenario_title'],
                'scenario_prompt': tf['scenario_prompt'],
                'interpretation': tf['interpretation'],
                'speech': tf['speech'],
                'action': tf['action'],
                'narrative': tf['narrative'],
                'threat_attribution_0_2': '',
                'benign_attribution_0_2': '',
                'memory_intrusion_0_2': '',
                'behavioral_avoidance_0_2': '',
                'mixed_attribution_0_1': '',
                'coder_notes': '',
            })
            mapping.append({
                'blind_order': idx,
                'blind_id': bid,
                'db_key': key,
                'db_path': str(path.relative_to(self.base)),
                'table': 'trials',
                'rowid': rowid,
                'trial_id': rec.get('id'),
                'row_hash': digest(raw_dict),
                'batch_id': rec.get('batch_id'),
                'protocol': rec.get('protocol'),
                'source': rec.get('source'),
                'model': rec.get('model'),
                'condition': rec.get('condition') or rec.get('condition_id'),
                'prompt_variant': rec.get('prompt_variant'),
                'temporal_variant': rec.get('temporal_variant'),
                'legacy_interpretation': mc.get('interpretation'),
                'legacy_action': mc.get('action'),
            })

        return '\ufeff' + buf.getvalue(), {
            'notice': 'DO_NOT_GIVE_TO_BLIND_CODERS — keep in private_inputs/ per WORKFLOW_SOP.md Section A3.',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'seed': seed,
            'db_key': key,
            'db_path': str(path.relative_to(self.base)),
            'batch_id': batch_id or 'ALL',
            'source_filter': source,
            'count': len(mapping),
            'mapping': mapping,
        }

    def export_pairing_csv(self, key, batch_id='', mode='auto'):
        data = self.pairs(key, batch_id=batch_id, mode=mode)
        buf = io.StringIO()
        fields = [
            'pair_id', 'left_id', 'right_id', 'block_id', 'reason', 'missing_side',
            'condition', 'scenario_id', 'left_rowid', 'right_rowid',
            'left_legacy_interpretation', 'right_legacy_interpretation', 'label_changed',
        ]
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for p in data['pairs']:
            left, right = p['left'], p['right']
            writer.writerow({
                'pair_id': p['pair_id'],
                'left_id': left['id'] if left else '',
                'right_id': right['id'] if right else '',
                'block_id': p['block_id'],
                'reason': p['reason'],
                'missing_side': p['missing_side'],
                'condition': p['condition'],
                'scenario_id': p['scenario_id'],
                'left_rowid': left['rowid'] if left else '',
                'right_rowid': right['rowid'] if right else '',
                'left_legacy_interpretation': left['legacy_interpretation'] if left else '',
                'right_legacy_interpretation': right['legacy_interpretation'] if right else '',
                'label_changed': p['label_changed'],
            })
        return '\ufeff' + buf.getvalue()

    def export_reviews_csv(self):
        latest = self.latest_reviews_map()
        buf = io.StringIO()
        fields = [
            'path', 'db', 'table', 'rowid', 'row_hash', 'reviewer', 'decision', 'note',
            'threat_attribution', 'benign_attribution', 'memory_intrusion',
            'behavioral_avoidance', 'mixed_attribution', 'coding_mode',
            'inventory_id', 'created_at',
        ]
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for ev in sorted(latest.values(), key=lambda x: (x.get('path') or '', x.get('table') or '', int(x.get('rowid') or 0))):
            c = ev.get('coding') if isinstance(ev.get('coding'), dict) else {}
            writer.writerow({
                'path': ev.get('path', ''),
                'db': ev.get('db', ''),
                'table': ev.get('table', ''),
                'rowid': ev.get('rowid', ''),
                'row_hash': ev.get('row_hash', ''),
                'reviewer': ev.get('reviewer', ''),
                'decision': ev.get('decision', ''),
                'note': ev.get('note', ''),
                'threat_attribution': '' if c.get('threat_attribution') is None else c.get('threat_attribution'),
                'benign_attribution': '' if c.get('benign_attribution') is None else c.get('benign_attribution'),
                'memory_intrusion': '' if c.get('memory_intrusion') is None else c.get('memory_intrusion'),
                'behavioral_avoidance': '' if c.get('behavioral_avoidance') is None else c.get('behavioral_avoidance'),
                'mixed_attribution': '' if 'mixed_attribution' not in c else c.get('mixed_attribution'),
                'coding_mode': c.get('coding_mode', ''),
                'inventory_id': ev.get('inventory_id', ''),
                'created_at': ev.get('created_at', ''),
            })
        return '\ufeff' + buf.getvalue()

    def reviews(self):
        self.output.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.output / 'reviews.sqlite3')
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, created_at TEXT, payload TEXT)')
        db.executescript("""
            CREATE TRIGGER IF NOT EXISTS review_no_update BEFORE UPDATE ON reviews
            BEGIN SELECT RAISE(ABORT,'append-only review history'); END;
            CREATE TRIGGER IF NOT EXISTS review_no_delete BEFORE DELETE ON reviews
            BEGIN SELECT RAISE(ABORT,'append-only review history'); END;
        """)
        return db

    def save_review(self, value):
        required = ('db', 'table', 'rowid', 'row_hash', 'reviewer', 'decision', 'note')
        if any(k not in value for k in required):
            raise ValueError('Missing review field')
        if not value['reviewer'].strip() or not value['note'].strip():
            raise ValueError('Reviewer and evidence note required')
        if value['decision'] not in ('include', 'exclude', 'uncertain'):
            raise ValueError('Invalid decision')
        row = self.row(value['db'], value['table'], value['rowid'])
        if digest(row) != value['row_hash']:
            raise ValueError('Source row changed; reload before saving')
        record = {k: value[k] for k in required}
        if 'coding' in value and value['coding'] is not None:
            record['coding'] = _validate_coding(value['coding'])
        record['path'] = str(self.paths[value['db']].relative_to(self.base))
        record['inventory_id'] = (self.report or {}).get('inventory_id')
        record['created_at'] = datetime.now(timezone.utc).isoformat()
        with closing(self.reviews()) as db:
            with db:
                db.execute('INSERT INTO reviews(created_at,payload) VALUES (?,?)', (record['created_at'], json.dumps(record, ensure_ascii=False)))
        return record

    def freeze_reviews(self, destination):
        """Freeze all events plus latest decisions; stale entries stay visibly stale."""
        destination = Path(destination)
        if destination.exists():
            raise ValueError('Decision freeze already exists')
        with closing(self.reviews()) as db:
            events = [json.loads(r[0]) for r in db.execute('SELECT payload FROM reviews ORDER BY id')]
        latest = {}
        for event in events:
            latest[(event['db'], event['table'], str(event['rowid']))] = event
        decisions = []
        for event in latest.values():
            item = dict(event)
            try:
                item['source_state'] = ('current' if digest(self.row(event['db'], event['table'], event['rowid'])) == event['row_hash'] else 'changed')
            except (KeyError, ValueError, sqlite3.Error, OSError):
                item['source_state'] = 'unavailable'
            decisions.append(item)
        result = {
            'inventory_id': (self.report or {}).get('inventory_id'),
            'created_at': datetime.now(timezone.utc).isoformat(), 'events': events,
            'latest_decisions': decisions, 'note': 'Unreviewed rows have no decision; this is not an analysis sample.',
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return result


def handler(audit, port):
    class Handler(BaseHTTPRequestHandler):
        def send(self, value, status=200, mime='application/json; charset=utf-8', attachment=None):
            body = (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header(
                'Content-Security-Policy',
                "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            )
            if attachment:
                self.send_header('Content-Disposition', f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(body)

        def local(self):
            return self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}')

        def do_GET(self):
            if not self.local():
                return self.send({'error': 'Invalid host'}, 403)
            url = urlsplit(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path in STATIC_FILES:
                    rel, mime = STATIC_FILES[url.path]
                    return self.send((ROOT / rel).read_text(encoding='utf-8'), mime=mime)
                if url.path == '/workflow':
                    return self.send((ROOT / 'WORKFLOW_SOP.md').read_text(encoding='utf-8'), mime='text/plain; charset=utf-8')
                if url.path == '/api/inventory':
                    return self.send(audit.report)
                if url.path == '/api/rows':
                    return self.send(
                        audit.rows(
                            q['db'],
                            q['table'],
                            q.get('offset', 0),
                            q.get('query', ''),
                            batch_id=q.get('batch_id', ''),
                            source=q.get('source', ''),
                            status=q.get('status', ''),
                            flag=q.get('flag', ''),
                            review_status=q.get('review_status', ''),
                            limit=q.get('limit', 40),
                        )
                    )
                if url.path == '/api/row':
                    return self.send(audit.row_detail(q['db'], q['table'], q['rowid']))
                if url.path == '/api/reviews':
                    with closing(audit.reviews()) as db:
                        rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM reviews ORDER BY id')]
                    return self.send(rows)
                if url.path == '/api/pairs':
                    return self.send(audit.pairs(q['db'], batch_id=q.get('batch_id', ''), mode=q.get('mode', 'auto')))
                if url.path == '/api/rr-summary':
                    return self.send(audit.rr_summary(q['db']))
                if url.path == '/api/export/reviews.csv':
                    return self.send(audit.export_reviews_csv(), mime='text/csv; charset=utf-8', attachment='echomind-latest-reviews.csv')
                if url.path == '/api/export/pairing.csv':
                    csv_body = audit.export_pairing_csv(q['db'], batch_id=q.get('batch_id', ''), mode=q.get('mode', 'auto'))
                    return self.send(csv_body, mime='text/csv; charset=utf-8', attachment='pairing.csv')
                if url.path == '/api/export/blind-packet.csv':
                    csv_body, _ = audit.export_blind_packet(
                        q['db'], batch_id=q.get('batch_id', ''), source=q.get('source', 'LIVE_LLM_API'), seed=q.get('seed', 'echomind-blind-v1')
                    )
                    return self.send(csv_body, mime='text/csv; charset=utf-8', attachment='blind-coding-packet.csv')
                if url.path == '/api/export/blind-mapping.json':
                    _, mapping = audit.export_blind_packet(
                        q['db'], batch_id=q.get('batch_id', ''), source=q.get('source', 'LIVE_LLM_API'), seed=q.get('seed', 'echomind-blind-v1')
                    )
                    return self.send(mapping, attachment='blind-mapping-DO-NOT-SHARE.json')
                return self.send({'error': 'Not found'}, 404)
            except (ValueError, KeyError, sqlite3.Error) as exc:
                return self.send({'error': str(exc)}, 400)

        def do_POST(self):
            if not self.local() or self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
                return self.send({'error': 'Local origin required'}, 403)
            route = urlsplit(self.path).path
            try:
                if route == '/api/rescan':
                    return self.send(audit.scan())
                if route != '/api/review':
                    return self.send({'error': 'Not found'}, 404)
                n = int(self.headers.get('Content-Length', '0'))
                if n < 1 or n > 40000:
                    raise ValueError('Invalid body size')
                return self.send(audit.save_review(json.loads(self.rfile.read(n))))
            except (ValueError, KeyError, TypeError, AttributeError, sqlite3.Error) as exc:
                return self.send({'error': str(exc)}, 400)

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, default=ROOT)
    parser.add_argument('--port', type=int, default=8770)
    parser.add_argument('--scan-only', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    audit = Audit(args.base)
    report = audit.scan()
    print(f"Scanned {len(report['databases'])} databases; {report['unique_trial_ids']} trial IDs; {len(report['conflicts'])} conflicting IDs", flush=True)
    if args.scan_only:
        return
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(audit, args.port))
    print(f'EchoMind data audit: http://127.0.0.1:{args.port}/', flush=True)
    if not args.no_browser:
        threading.Timer(.5, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}/')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
