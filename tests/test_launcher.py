"""Check workspace isolation without opening a real browser or model API."""
import contextlib
import io
import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import launch_demo
from echomind.model_client import offline_mode


class LauncherTests(unittest.TestCase):
    def health(self, **overrides):
        return {"version": "research-repair-v1", "workspace_root": str(ROOT),
                "database": str(ROOT / "data" / "pilot.sqlite3"),
                "code_revision": "same-code", "offline": True, **overrides}

    def invoke_running(self, health):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(json.dumps(health).encode())
        with patch("launch_demo.urllib.request.build_opener", return_value=opener), \
             patch("launch_demo.local_revision", return_value="same-code"), \
             patch("launch_demo.webbrowser.open") as browser, \
             patch("launch_demo.subprocess.call") as process, \
             patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()):
            result = launch_demo.main(["--offline"])
        return result, browser, process

    def test_reopens_only_same_workspace_database_revision_and_mode(self):
        result, browser, process = self.invoke_running(self.health())
        self.assertEqual(result, 0)
        browser.assert_called_once_with(launch_demo.URL)
        process.assert_not_called()

    def test_refuses_other_workspaces_databases_revisions_and_online_servers(self):
        for overrides in [
            {"workspace_root": str(ROOT.parent / "SOS")},
            {"database": str(ROOT.parent / "SOS" / "data" / "pilot.sqlite3")},
            {"code_revision": "old-code"},
            {"offline": False},
        ]:
            with self.subTest(overrides=overrides):
                result, browser, process = self.invoke_running(self.health(**overrides))
                self.assertEqual(result, 1)
                browser.assert_not_called()
                process.assert_not_called()

    def test_start_pins_own_database_even_with_inherited_override(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.URLError("no local server")
        with patch("launch_demo.urllib.request.build_opener", return_value=opener), \
             patch("launch_demo.subprocess.call", return_value=0) as process, \
             patch.dict(os.environ, {"SOS_PILOT_DB": "old-sos.sqlite3", "ECHOMIND_PILOT_DB": "another.sqlite3"}, clear=True):
            self.assertEqual(launch_demo.main(["--offline"]), 0)
        args, kwargs = process.call_args
        self.assertIn("--offline", args[0])
        self.assertEqual(kwargs["cwd"], str(ROOT))
        self.assertEqual(kwargs["env"]["ECHOMIND_PILOT_DB"], str(ROOT / "data" / "pilot.sqlite3"))

    def test_only_echomind_offline_environment_is_used(self):
        for env, expected in [({}, False), ({"ECHOMIND_OFFLINE": "1"}, True),
                              ({"SOS_OFFLINE": "1"}, False),
                              ({"ECHOMIND_OFFLINE": "0", "SOS_OFFLINE": "1"}, False)]:
            with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                self.assertEqual(offline_mode(), expected)


if __name__ == "__main__":
    unittest.main()
