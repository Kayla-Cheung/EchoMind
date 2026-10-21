"""Smoke checks for the unified local UI without any paid API requests."""
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


class UnifiedUiTests(unittest.TestCase):
    def test_unique_ids_and_script_scoping(self):
        html = (ROOT / 'web/unified.html').read_text(encoding='utf-8')
        ids = re.findall(r'\bid="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('role="tablist"', html)
        self.assertIn('id="view-mechanism"', html)
        self.assertIn('id="view-ablation"', html)
        self.assertIn('id="abl-run"', html)
        self.assertIn('id="run"', html)
        self.assertIn('/unified.js', html)
        mechanism_js = (ROOT/'web/mechanism.js').read_text(encoding='utf-8')
        ablation_js = (ROOT/'web/ablation.js').read_text(encoding='utf-8')
        self.assertTrue(mechanism_js.startswith('(() => {'))
        self.assertTrue(ablation_js.startswith('(() => {'))
        self.assertIn("document.getElementById('abl-' + id)", ablation_js)

    def test_http_routes_share_html(self):
        with tempfile.TemporaryDirectory() as directory:
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.close()
            env = dict(os.environ, SOS_PILOT_DB=str(Path(directory)/'only-test.sqlite3'))
            process = subprocess.Popen([sys.executable, '-u', 'server.py', '--port', str(port)],
                                      cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                def fetch(path):
                    with urlopen(f'http://127.0.0.1:{port}{path}', timeout=4) as response:
                        return response.status, response.read()
                for _ in range(60):
                    try:
                        if fetch('/')[0] == 200:
                            break
                    except Exception:
                        time.sleep(.1)
                else:
                    self.fail('Local server did not start')
                root = fetch('/')[1]
                self.assertEqual(root, fetch('/ablation')[1])
                self.assertIn(b'id="tab-ablation"', root)
                for asset in ('unified.js','unified.css','ablation.js','mechanism.js'):
                    code, data = fetch('/' + asset)
                    self.assertEqual(code, 200)
                    self.assertGreater(len(data), 300)
            finally:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill()


if __name__ == '__main__':
    unittest.main()
