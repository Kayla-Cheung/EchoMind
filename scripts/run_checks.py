"""Public, no-paid-API verification; frozen versions run in separate processes."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
HTTP_CLASSES = (
    "test_ablation.AblationHTTP.", "test_acquisition_http.AcquisitionHTTPTests.",
    "test_measurement.MeasurementHTTP.", "test_pilot.HttpTests.",
    "test_research_repair.HistoryHTTPTests.",
    "test_server_security.ServerSecurityTests.",
)
HTTP_METHODS = {"test_unified_ui.UnifiedUiTests.test_http_routes_share_html"}


def is_http(test_id: str) -> bool:
    return test_id.startswith(HTTP_CLASSES) or test_id in HTTP_METHODS


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def loopback_check():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"echomind-check")

        def log_message(self, *_):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        worker = threading.Thread(target=server.handle_request, daemon=True)
        worker.start()
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f"http://127.0.0.1:{server.server_port}/", timeout=2) as response:
                if response.read() != b"echomind-check":
                    raise OSError("Unexpected loopback response")
        finally:
            worker.join(timeout=3)


def run_core(include_http: bool) -> int:
    sys.path.insert(0, str(ROOT))
    discovered = list(flatten(unittest.defaultTestLoader.discover(str(ROOT / "tests"))))
    selected, excluded = [], []
    for test in discovered:
        (excluded if not include_http and is_http(test.id()) else selected).append(test)
    print(f"Core: {len(selected)} selected; {len(excluded)} localhost tests excluded", flush=True)
    for test in excluded:
        print("EXCLUDED: " + test.id(), flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    return int(not result.wasSuccessful())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", action="store_true", help="Also check each frozen version in isolation")
    parser.add_argument("--http", action="store_true", help="Require localhost integration tests")
    parser.add_argument("--core-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.core_only:
        return run_core(args.http)
    if args.http:
        try:
            loopback_check()
        except OSError as exc:
            print(f"HTTP scope requested but loopback is unavailable: {exc}", file=sys.stderr)
            return 1
    env = dict(os.environ)
    for name in list(env):
        if name.upper().endswith("_API_KEY"):
            env.pop(name)
    env.update(ECHOMIND_OFFLINE="1", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    jobs = [
        ("Repository audit", ROOT, [str(ROOT / "scripts/check_repository.py")]),
        ("Core unit tests", ROOT, [str(Path(__file__).resolve()), "--core-only", *(["--http"] if args.http else [])]),
    ]
    if args.snapshots:
        for version in ("v03-prompt-framing", "v04-temporal-context"):
            jobs.append((version + " acquisition tests", ROOT / "experiments" / version,
                         ["-m", "unittest", "discover", "-s", "tests", "-p", "test_acquisition.py", "-v"]))
        for version in ("v05-human-rr", "rr-isolation"):
            jobs.append((version + " synthetic protocol smoke", ROOT,
                         [str(ROOT / "scripts/smoke_rr.py"), "--experiment", version]))
    failed = []
    for label, directory, command in jobs:
        print(f"\nRunning: {label}", flush=True)
        try:
            result = subprocess.run([sys.executable, *command], cwd=directory, env=env, timeout=240)
            passed = result.returncode == 0
        except subprocess.TimeoutExpired:
            passed = False
            print("TIMEOUT: " + label, file=sys.stderr)
        if not passed:
            failed.append(label)
    print(f"\nScopes: {len(jobs) - len(failed)} passed / {len(jobs)} total", flush=True)
    for label in failed:
        print("FAILED SCOPE: " + label, file=sys.stderr)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
