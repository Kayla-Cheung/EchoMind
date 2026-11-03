"""Open EchoMind only when the server belongs to this workspace and database."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8769
URL = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parent


def local_revision():
    paths = sorted((ROOT / "echomind").glob("*.py")) + sorted((ROOT / "web").glob("*.*"))
    return hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in paths)).hexdigest()[:16]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open the EchoMind workspace in this folder.")
    parser.add_argument("--offline", action="store_true", help="Disable credential loading and live API calls.")
    args = parser.parse_args(argv)
    database = (ROOT / "data" / "pilot.sqlite3").resolve()
    offline = args.offline or os.getenv("ECHOMIND_OFFLINE") == "1"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(URL + "/api/health", timeout=2) as response:
            info = json.load(response)
            running = True
    except (OSError, ValueError):
        running = False
    if running:
        same_workspace = (info.get("version") == "research-repair-v1"
                          and Path(info.get("workspace_root", "")).resolve() == ROOT
                          and Path(info.get("database", "")).resolve() == database)
        if not same_workspace:
            print(f"Port {PORT} is serving another workspace. Stop that server before opening EchoMind.")
            print("EchoMind database: " + str(database))
            return 1
        if info.get("code_revision") != local_revision():
            print("EchoMind source files changed. Stop the existing server and restart.")
            return 1
        if bool(info.get("offline")) != offline:
            print("The running server uses a different offline mode. Stop it and restart with the desired launcher.")
            return 1
        webbrowser.open(URL)
        print("EchoMind is already running: " + URL)
        return 0
    env = dict(os.environ)
    # Pin this launcher to the database belonging to this EchoMind folder.
    env["ECHOMIND_PILOT_DB"] = str(database)
    command = [sys.executable, "-u", str(ROOT / "server.py"), "--port", str(PORT), "--open-browser"]
    if offline:
        command.append("--offline")
    return subprocess.call(command, cwd=str(ROOT), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
