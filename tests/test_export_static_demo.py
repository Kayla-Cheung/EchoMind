import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import acquisition
import export_static_demo
import fetch_human_benchmark
from storage import Store


class ExportStaticDemoTests(unittest.TestCase):
    def test_export_is_strictly_readonly_and_preserves_failed_and_mock_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            store = Store(db_path)
            live_ok = {
                "id": "live-1",
                "timestamp": "2026-10-28T00:00:00+00:00",
                "batch_id": "batch-live",
                "source": "LIVE_LLM_API",
                "status": "complete",
                "protocol": acquisition.PROTOCOL_ID,
                "condition": "negative_direct",
                "scenario_id": "S1_near",
                "model": "deepseek-flash",
                "narrative": "测试文本</script><img src=x onerror=alert(1)>",
                "machine_coding": {
                    "interpretation": "neutral",
                    "action": "wait",
                    "coding_confidence": 0.9,
                    "coding_reason": "包含</script>与<tag>",
                },
            }
            live_err = {
                "id": "live-2",
                "timestamp": "2026-10-28T00:01:00+00:00",
                "batch_id": "batch-live",
                "source": "LIVE_LLM_API",
                "status": "error",
                "protocol": acquisition.PROTOCOL_ID,
                "condition": "negative_direct",
                "scenario_id": "S1_near",
                "model": "deepseek-flash",
                "error": "timeout",
            }
            mock_rec = {
                "id": "mock-1",
                "timestamp": "2026-10-28T00:02:00+00:00",
                "batch_id": "batch-mock",
                "source": "MOCK_NOT_LLM",
                "status": "complete",
                "protocol": acquisition.PROTOCOL_ID,
                "condition": "none",
                "scenario_id": "S1_near",
                "model": "deepseek-flash",
                "narrative": "mock text",
                "machine_coding": {"interpretation": "negative", "action": "avoid"},
            }
            for rec in (live_ok, live_err, mock_rec):
                store.add_trial(rec)

            before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()
            out_html = Path(tmp) / "report.html"
            report = export_static_demo.export_report(db_path, outputs=(out_html,))
            after_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

            # Database file must be completely untouched.
            self.assertEqual(before_hash, after_hash)
            self.assertEqual(len(store.trials()), 3)

            # Live trials keep both complete and error records; mock is excluded read-only.
            self.assertEqual(report["summary_meta"]["total_live_records"], 2)
            self.assertEqual(report["summary_meta"]["complete_live_records"], 1)
            self.assertEqual(report["summary_meta"]["failed_live_records"], 1)
            self.assertEqual(report["summary_meta"]["mock_records_excluded_readonly"], 1)

            row = report["overall_matrix"][0]
            self.assertEqual(row["total"], 2)
            self.assertEqual(row["complete"], 1)
            self.assertEqual(row["failed"], 1)
            self.assertEqual(row["neg_rate"], 0.0)
            self.assertEqual(row["avoid_rate"], 0.0)

            # Canonical materials match acquisition.py EVENTS and reject outdated fabricated text.
            neg_direct_text = report["prompt_inspector"]["memory_materials"]["negative_direct"]["text"]
            self.assertIn("核对一份三页的课程报告", neg_direct_text)
            self.assertNotIn("把案例放在前一部分", neg_direct_text)
            self.assertNotIn("皱了皱眉", neg_direct_text)

            # Generated HTML must escape </script> and never contain fabricated benchmark claims.
            html = out_html.read_text(encoding="utf-8")
            self.assertEqual(html.count("</script>"), 1)
            self.assertIn("\\u003c/script\\u003e", html)
            self.assertNotIn("负面 75%~85%", html)
            self.assertNotIn("符合人类心理规律", html)
            self.assertNotIn("humanBenchmarkTable", html)

            # Verify inline JS parses cleanly when node is installed.
            if shutil.which("node"):
                match = re.search(r"<script>(.*)</script>", html, re.S)
                self.assertIsNotNone(match)
                js_path = Path(tmp) / "inline.js"
                js_path.write_text(match.group(1), encoding="utf-8")
                res = subprocess.run(["node", "--check", str(js_path)], capture_output=True)
                self.assertEqual(res.returncode, 0, res.stderr.decode("utf-8", errors="replace"))

    def test_fetch_human_benchmark_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertEqual(
                fetch_human_benchmark._safe_child_path(base, "data.csv"),
                (base / "data.csv").resolve(),
            )
            for bad in ("", ".", "..", "../escape.txt", "a/b.txt", "a\\b.txt", "C:evil.txt"):
                with self.assertRaises(ValueError):
                    fetch_human_benchmark._safe_child_path(base, bad)


if __name__ == "__main__":
    unittest.main()
