"""Preview or explicitly run the existing workbench's acquisition protocol."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

import acquisition
from runner import JobManager, plan
from storage import Store
from history import reject_secrets

ROOT = Path(__file__).resolve().parent


def serve(database, port):
    database = Path(database).expanduser()
    database = (database if database.is_absolute() else ROOT / database).resolve()
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + "/api/health", timeout=2) as response:
            health = json.load(response)
    except (OSError, ValueError):
        health = None
    if health is not None:
        files = sorted(ROOT.glob("*.py")) + sorted((ROOT / "web").glob("*.*"))
        revision = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in files)).hexdigest()[:16]
        if (health.get("workspace_root") != str(ROOT) or health.get("database") != str(database) or health.get("code_revision") != revision
                or not health.get("offline") or "temporal_context_v04" not in health.get("capabilities", [])):
            print("This port serves another configuration or an older server. Close that server yourself before restarting.")
            return 1
        webbrowser.open(url + "/#acquisition")
        print("EchoMind Memory Acquisition MVP is already running: " + url + "/#acquisition")
        return 0
    env = {**os.environ, "ECHOMIND_PILOT_DB": str(database), "ECHOMIND_OFFLINE": "1"}
    return subprocess.call([sys.executable, str(ROOT / "server.py"), "--offline", "--port", str(port),
                            "--open-browser", "--open-path", "/#acquisition"], cwd=ROOT, env=env)


def main():
    parser = argparse.ArgumentParser(description="Memory Acquisition MVP v0.2; default preview/MOCK, no automatic REAL.")
    parser.add_argument("--db", default=str(ROOT / "data" / "temporal-context-v04.sqlite3"))
    parser.add_argument("--request", type=Path, help="Frozen configuration JSON; never put API keys here.")
    parser.add_argument("--run", action="store_true", help="Run after preview; otherwise only preview.")
    parser.add_argument("--serve", action="store_true", help="Open this database in the offline workbench; no experiment is started.")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--confirm-live", action="store_true", help="Explicitly authorize this configured REAL batch.")
    parser.add_argument("--output", type=Path, help="Write full preview/audit JSON to a NEW file.")
    args = parser.parse_args()
    if args.serve:
        if args.run or args.request or args.confirm_live:
            parser.error("--serve is only an offline browser launcher; configure experiments in the workbench.")
        return serve(args.db, args.port)
    if args.output and args.output.exists():
        parser.error("Output already exists; choose a new filename.")
    request = json.loads(args.request.read_text(encoding="utf-8-sig")) if args.request else {"mode": "mock"}
    if not isinstance(request, dict):
        parser.error("Request configuration must be a JSON object.")
    reject_secrets(request)
    request["protocol"] = acquisition.PROTOCOL_ID
    if request.get("mode", "mock") == "live":
        if args.run and not args.confirm_live:
            parser.error("REAL requires --confirm-live as well as --run; preview does not call APIs.")
        request["confirm_live"] = args.confirm_live
    else:
        os.environ["ECHOMIND_OFFLINE"] = "1"
    store = Store(args.db)
    prepared = plan(store.design(), request)
    result = acquisition.preview(prepared)
    print(f"Preview: {prepared['calls']} decisions, {prepared['acquisition_calls']} acquisitions, "
          f"{prepared['coding_calls']} codings; {prepared['mode']} / {prepared['phase']}")
    if args.run:
        request["preview_hash"] = prepared["preview_hash"]
        manager = JobManager(store)
        job = manager.start(request)
        try:
            while job["status"] in ("queued", "running"):
                time.sleep(.2)
                job = manager.get(job["id"])
        except KeyboardInterrupt:
            manager.cancel(job["id"])
            while manager.get(job["id"])["status"] in ("queued", "running"):
                time.sleep(.2)
            job = manager.get(job["id"])
        result = acquisition.export_batch(store, job["id"])
        print(json.dumps({k: job.get(k) for k in ("id", "status", "completed", "failed", "unissued", "api_attempts", "simulated_attempts", "stop_reason")}, ensure_ascii=False))
    if args.output:
        with args.output.open("x", encoding="utf-8") as target:
            json.dump(result, target, ensure_ascii=False, indent=2)
        print("Saved: " + str(args.output))
    return 0 if not args.run or result["job"]["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
