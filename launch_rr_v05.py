"""Start a detached, local-only RR workbench and verify its identity before opening it."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from rr_v05 import sha256_text


ROOT = Path(__file__).resolve().parent


def probe(url):
    # A local service must not depend on system HTTP proxy configuration.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + "api/health", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def matches(health, db_path, stimuli_path):
    return isinstance(health, dict) and (
        health.get("protocol") == "human_rr_v05"
        and health.get("status") == "ready"
        and health.get("workspace_id") == sha256_text(str(ROOT.resolve()))
        and health.get("database") == str(db_path)
        and health.get("stimuli") == str(stimuli_path)
    )


def start(port=8780, open_browser=True):
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be between 1024 and 65535")
    db_path = ROOT / "data" / "human-rr-v05.sqlite3"
    stimuli_path = ROOT / "private_inputs" / "calm_rr_v42.json"
    if not stimuli_path.is_file():
        raise RuntimeError("Missing local stimuli: private_inputs/calm_rr_v42.json")
    url = f"http://127.0.0.1:{port}/"
    health = probe(url)
    if health is not None and not matches(health, db_path, stimuli_path):
        raise RuntimeError(f"Port {port} serves another workspace; choose another port.")
    if not matches(health, db_path, stimuli_path):
        interpreter = Path(sys.executable)
        kwargs = {}
        if os.name == "nt":
            candidate = interpreter.with_name("pythonw.exe")
            if candidate.is_file():
                interpreter = candidate
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        log_dir = ROOT / "private_exports"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "rr-workbench.log"
        with log_path.open("ab", buffering=0) as log:
            child = subprocess.Popen(
                [str(interpreter), "-u", str(ROOT / "rr_workbench.py"), "--host", "127.0.0.1",
                 "--port", str(port), "--db", str(db_path), "--stimuli", str(stimuli_path)],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, **kwargs,
            )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if matches(probe(url), db_path, stimuli_path):
                break
            if child.poll() is not None:
                raise RuntimeError(f"Workbench exited ({child.returncode}). See private_exports/rr-workbench.log. "
                                   f"Port {port} may be occupied by an unresponsive process.")
            time.sleep(0.2)
        else:
            # This launcher owns the new process. Do not touch an existing port owner.
            child.terminate()
            raise RuntimeError("Workbench did not become ready. See private_exports/rr-workbench.log.")
    if open_browser:
        webbrowser.open(url)
    return url


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        print("EchoMind v0.5 ready: " + start(args.port, not args.no_browser))
    except Exception as exc:
        print(f"Could not start EchoMind v0.5: {exc}", file=sys.stderr)
        sys.exit(1)
