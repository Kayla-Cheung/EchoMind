"""Regression checks for publication boundaries and test-scope selection."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.check_repository import forbidden_path, local_path, notebook_errors, public_paths
from scripts.run_checks import is_http


class RepositoryToolsTests(unittest.TestCase):
    def test_staged_ignored_files_are_still_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gitignore").write_text(".env\nrr.csv\n", encoding="utf-8")
            (root / ".env").write_text("TEST_ONLY=synthetic\n", encoding="utf-8")
            (root / "rr.csv").write_text("synthetic_fixture\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
            subprocess.run(["git", "add", "--force", ".env"], cwd=root, check=True, capture_output=True)
            paths = public_paths(root)
            self.assertIn(".env", paths)
            self.assertTrue(forbidden_path(".env"))
            self.assertNotIn("rr.csv", paths)

    def test_public_metadata_is_allowed_but_human_and_private_files_are_not(self):
        for name in ("data/scenarios.json", "experiments/v05-human-rr/data/rr_v05_source_manifest.json", ".env.example"):
            self.assertFalse(forbidden_path(name), name)
        for name in ("data/rr.csv", "human-analysis/data/raw/rr.csv", "experiments/v05-human-rr/private_inputs/stimuli.json",
                     "private_exports/result.json", ".env.local", "data/nested/scenarios.json", "pilot.sqlite3", "trace.jsonl",
                     "rr.csv", "smoke-live-round2.json", "ratings-real-example.csv", "split_salt.txt"):
            self.assertTrue(forbidden_path(name), name)

    def test_cross_platform_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ("../outside", "/absolute", "C:/outside", "sub/../../outside", "sub\\outside", ""):
                with self.assertRaises(ValueError, msg=value):
                    local_path(root, value)
            self.assertEqual(local_path(root, "configs/example.json"), root / "configs/example.json")

    def test_notebook_execution_metadata_is_detected(self):
        clean = {"cells": [{"cell_type": "code", "execution_count": None, "outputs": []}]}
        self.assertEqual(notebook_errors(clean), [])
        clean["cells"][0]["execution_count"] = 1
        self.assertEqual(len(notebook_errors(clean)), 1)
        clean["cells"][0].update(execution_count=None, outputs=[{"output_type": "stream", "text": "private"}])
        self.assertEqual(len(notebook_errors(clean)), 1)

    def test_http_selection_retains_unrelated_logic_tests(self):
        self.assertTrue(is_http("test_server_security.ServerSecurityTests.test_post_blocks_cross_origin_cross_site_and_non_json_requests"))
        self.assertTrue(is_http("test_pilot.HttpTests.test_end_to_end_mock_save_edit_export"))
        self.assertTrue(is_http("test_unified_ui.UnifiedUiTests.test_http_routes_share_html"))
        self.assertFalse(is_http("test_pilot.LogicTests.test_clean_role_and_blind_coder"))
        self.assertFalse(is_http("test_unified_ui.UnifiedUiTests.test_unique_ids_and_script_scoping"))
