"""Local-only v0.5 RR workbench and export server."""
from __future__ import annotations

import argparse
import csv
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from rr_v05 import SOCIAL_SCENARIOS, connect, load_stimuli, ordinal_wasserstein, public_batch, sha256_text


ROOT = Path(__file__).resolve().parent
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def latest_batch(db):
    row = db.execute("SELECT batch_id FROM batches ORDER BY created_at DESC LIMIT 1").fetchone()
    return row[0] if row else None


def result_payload(db, stimuli, batch_id):
    batch = public_batch(db, batch_id)
    human = {}
    for row in db.execute("SELECT human_column,n,distribution_json FROM human_reference WHERE batch_id=? AND split='heldout'", (batch_id,)):
        human[row["human_column"]] = {"n": row["n"], "probabilities": json.loads(row["distribution_json"])}
    conditions = {}
    for condition in batch["contexts"]:
        model = {}
        for row in db.execute("SELECT item_id,rating FROM ratings WHERE batch_id=? AND condition_id=?", (batch_id, condition)):
            model.setdefault(row["item_id"], []).append(row["rating"])
        conditions[condition] = {
            "rating_count": sum(len(x) for x in model.values()),
            "primary_social_target_distance": ordinal_wasserstein(model, human, stimuli, SOCIAL_SCENARIOS, ("ns", "ps")),
            "social_foil_distance": ordinal_wasserstein(model, human, stimuli, SOCIAL_SCENARIOS, ("nf", "pf")),
            "all_target_distance": ordinal_wasserstein(model, human, stimuli, {x["id"] for x in stimuli["scenarios"]}, ("ns", "ps")),
        }
    return {"batch": batch, "conditions": conditions, "metric": "ordinal Wasserstein distance on support 1..4; lower is closer"}


def handler(db_path, stimuli_path):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status, body, content_type, disposition=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def json(self, value, status=200):
            self.send_bytes(status, json.dumps(value, ensure_ascii=False, indent=2).encode(), "application/json; charset=utf-8")

        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/api/health":
                return self.json({"protocol": "human_rr_v05", "status": "ready",
                                  "workspace_id": sha256_text(str(ROOT.resolve())),
                                  "database": str(Path(db_path).resolve()),
                                  "stimuli": str(Path(stimuli_path).resolve())})
            if route in ("/", "/index.html"):
                route = "/rr_v05.html"
            if route in ("/rr_v05.html", "/rr_v05.js", "/rr_v05.css"):
                path = ROOT / "web" / route[1:]
                return self.send_bytes(200, path.read_bytes(), MIME[path.suffix])
            db = connect(db_path)
            try:
                batch_id = latest_batch(db)
                if route == "/api/status":
                    return self.json({"protocol": "human_rr_v05", "database": str(Path(db_path).resolve()),
                                      "stimuli_available": Path(stimuli_path).is_file(), "latest_batch": public_batch(db, batch_id) if batch_id else None})
                if route == "/api/measurement":
                    stimuli = load_stimuli(stimuli_path)
                    return self.json({"source": stimuli.get("source"), "stimulus_set_hash": stimuli["stimulus_set_hash"],
                                      "scale": {"1": "Very different", "2": "Different", "3": "Similar", "4": "Very similar"},
                                      "procedure": ["Read nine ambiguous stories without seeing choices", "Answer comprehension questions", "Rate 36 interpretations in source order"],
                                      "scenarios": stimuli["scenarios"]})
                if route == "/api/results":
                    if not batch_id:
                        return self.json({"batch": None, "conditions": {}})
                    return self.json(result_payload(db, load_stimuli(stimuli_path), batch_id))
                if route == "/api/export/raw.json":
                    if not batch_id:
                        return self.json({"error": "no batch"}, 404)
                    rows = [dict(row) for row in db.execute("SELECT * FROM requests WHERE batch_id=? ORDER BY created_at", (batch_id,))]
                    body = json.dumps({"batch": public_batch(db, batch_id), "requests": rows}, ensure_ascii=False, indent=2).encode()
                    return self.send_bytes(200, body, "application/json; charset=utf-8", f'attachment; filename="{batch_id}-raw.json"')
                if route == "/api/export/ratings.csv":
                    if not batch_id:
                        return self.json({"error": "no batch"}, 404)
                    output = io.StringIO(newline="")
                    columns = ["batch_id", "episode_id", "condition_id", "scenario_id", "scenario_category", "item_id", "rating_type", "rating", "source_stimulus_hash"]
                    writer = csv.DictWriter(output, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(dict(row) for row in db.execute("SELECT * FROM ratings WHERE batch_id=? ORDER BY condition_id,scenario_id,item_id", (batch_id,)))
                    return self.send_bytes(200, output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", f'attachment; filename="{batch_id}-ratings.csv"')
                return self.json({"error": "not found"}, 404)
            except Exception as exc:
                return self.json({"error": str(exc)}, 500)
            finally:
                db.close()

        def log_message(self, fmt, *args):
            print("RR workbench:", fmt % args)

    return Handler


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8780)
    p.add_argument("--db", default=str(ROOT / "data" / "human-rr-v05.sqlite3"))
    p.add_argument("--stimuli", default=str(ROOT / "private_inputs" / "calm_rr_v42.json"))
    args = p.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler(args.db, args.stimuli))
    print(f"EchoMind v0.5 RR workbench: http://{args.host}:{args.port}/")
    server.serve_forever()
