"""Security and error-handling tests for the local EchoMind HTTP server."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ServerSecurityTests(unittest.TestCase):
    def test_post_blocks_cross_origin_cross_site_and_non_json_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "security-test.sqlite3"
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            child = subprocess.Popen(
                [sys.executable, "-u", str(ROOT / "server.py"), "--offline", "--port", str(port)],
                cwd=str(ROOT),
                env={**os.environ, "ECHOMIND_OFFLINE": "1", "ECHOMIND_PILOT_DB": str(db_path)},
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(100):
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=2) as res:
                            if res.status == 200:
                                break
                    except OSError:
                        time.sleep(0.05)
                else:
                    self.fail("server did not start")

                payload = json.dumps({"source": "MOCK_NOT_LLM"}).encode("utf-8")

                # 1. Cross-origin POST must be blocked with 403
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/analysis",
                    data=payload,
                    headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    opener.open(req, timeout=5)
                self.assertEqual(ctx.exception.code, 403)

                # 2. Cross-site Sec-Fetch-Site must be blocked with 403
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/analysis",
                    data=payload,
                    headers={"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    opener.open(req, timeout=5)
                self.assertEqual(ctx.exception.code, 403)

                # 3. Non-JSON simple POST (form / text/plain CSRF) must be blocked with 403
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/analysis",
                    data=payload,
                    headers={"Content-Type": "text/plain"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    opener.open(req, timeout=5)
                self.assertEqual(ctx.exception.code, 403)

                # 4. Non-local Host (DNS rebinding) must be blocked with 403
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/health",
                    headers={"Host": f"evil.example:{port}"},
                    method="GET",
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    opener.open(req, timeout=5)
                self.assertEqual(ctx.exception.code, 403)

                # 5. Same-origin local JSON POST must succeed
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/analysis",
                    data=payload,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "Origin": f"http://127.0.0.1:{port}",
                        "Sec-Fetch-Site": "same-origin",
                    },
                    method="POST",
                )
                with opener.open(req, timeout=5) as res:
                    self.assertEqual(res.status, 200)
                    body = json.loads(res.read().decode("utf-8"))
                    self.assertEqual(body["source"], "MOCK_NOT_LLM")
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()


if __name__ == "__main__":
    unittest.main()
