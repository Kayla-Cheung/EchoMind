import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from channels import parse_channels, FORMAT_VERSION, CODER_VERSION
from design import initial_design
from mechanism import PROTOCOL_ID, RULE, fisher_exact, wilson, summarize_mechanism
from prompts import role_messages, evaluator_messages
from runner import plan, JobManager, execute_task
from state_protocol import CORE_STATES
from storage import Store


def request(repeats=20, mode="mock"):
    return {"protocol": PROTOCOL_ID, "mode": mode, "repeats": repeats,
            "models": [{"provider": "deepseek", "model": "deepseek-flash",
                        "thinking": "disabled", "temperature": 1}],
            "evaluator": {"provider": "deepseek", "model": "deepseek-flash",
                          "thinking": "disabled", "temperature": 0},
            "scenario_ids": ["S01"], "conditions": list(CORE_STATES), "variants": ["A"]}


def fixture_counts(negative=(0, 10, 20), avoid=(0, 10, 20), repeats=20):
    """Synthetic fixtures deliberately exercise decisions; not real API evidence."""
    rows = []
    for ci, condition in enumerate(CORE_STATES):
        for i in range(repeats):
            rows.append({
                "id": f"fixture-{ci}-{i}", "protocol": PROTOCOL_ID, "batch_id": "fixture",
                "source": "LIVE_LLM_API", "status": "complete", "condition": condition,
                "repeat": i+1, "schedule_index": len(rows)+1, "model": "fixture",
                "provider": "fixture", "evaluator_model": "fixture", "evaluator_provider": "fixture",
                "model_spec": {"model": "fixture"}, "evaluator_spec": {"model": "fixture"},
                "scenario_hash": "fixture-scene", "protocol_hash": "fixture-materials",
                "design_hash": "fixture-design", "induction_variant": "A",
                "prompt_hash": condition, "prompt_version": "fixture-v1",
                "coder_version": CODER_VERSION, "output_format": FORMAT_VERSION,
                "evidence_rule": copy.deepcopy(RULE),
                "snapshot": {"request": request(repeats), "scenario": {"id": "S01", "situation": "fixture"}},
                "channels": {"thought": "fixture", "speech": None, "behavior": "fixture"},
                "machine_coding": {"interpretation": "negative" if i < negative[ci] else "neutral",
                                   "action": "avoid" if i < avoid[ci] else "wait"},
            })
    return rows


class MechanismTests(unittest.TestCase):
    def test_optional_channels_and_malformed_output(self):
        self.assertEqual(parse_channels("内心想法：我想再看看。"),
                         {"thought": "我想再看看。", "speech": None, "behavior": None})
        self.assertEqual(parse_channels("内心想法：我不知道。\n说话：无\n行为：我等一会儿。")["speech"], None)
        self.assertEqual(parse_channels("内心想法: 我不明白。\n行为: 我退出。")["behavior"], "我退出。")
        for value in ("我直接回复。", "内心想法：\n行为：我等着。",
                      "内心想法：我想。\n内心想法：再想。", "说明\n内心想法：我想。",
                      "内心想法：我想。\n行为：我等。\n说话：你好。"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_channels(value)

    def test_fixed_question_clean_context_blind_coding(self):
        d = initial_design()
        prepared = plan(d, request())
        self.assertEqual(len(prepared["tasks"]), 60)
        prompts = {}
        for task in prepared["tasks"]:
            p = role_messages(d, task["scenario"], task["memories"], structured=True)
            prompts.setdefault(task["condition"], set()).add(p["prompt_hash"])
            text = json.dumps(p["messages"], ensure_ascii=False)
            for forbidden in ("state_none", "state_mild", "state_moderate", "目标轻度", "Claim"):
                self.assertNotIn(forbidden, text)
        self.assertTrue(all(len(hashes) == 1 for hashes in prompts.values()))
        self.assertEqual(len({next(iter(s)) for s in prompts.values()}), 3)
        task = prepared["tasks"][0]
        coder = evaluator_messages(task["scenario"], "内心想法：我不清楚。", d["coding_rules"], structured=True)
        coder_text = json.dumps(coder, ensure_ascii=False)
        for memory in task["memories"]:
            self.assertNotIn(memory["text"], coder_text)
        self.assertNotIn("state_", coder_text)
        for changes in ({"scenario_ids": ["S01", "S03"]}, {"variants": ["A", "B"]},
                        {"conditions": ["state_none"]}, {"repeats": 101}):
            with self.assertRaises(ValueError):
                plan(d, {**request(), **changes})

    def test_reference_statistics_and_edges(self):
        # Published independent reference example: [[6,2],[1,4]].
        self.assertAlmostEqual(fisher_exact(6, 8, 1, 5), 0.10256410256410257, places=14)
        self.assertAlmostEqual(fisher_exact(8, 10, 1, 6), 0.034965034965034975, places=14)
        self.assertEqual(fisher_exact(10, 20, 10, 20), 1.0)
        self.assertEqual(fisher_exact(0, 20, 0, 20), 1.0)
        self.assertIsNone(fisher_exact(0, 0, 1, 2))
        self.assertLess(fisher_exact(0, 100, 100, 100), 1e-50)
        lower, upper = wilson(0, 20)
        self.assertAlmostEqual(lower, 0)
        self.assertAlmostEqual(upper, .16112515805281938)
        self.assertIsNone(wilson(0, 0))

    def test_support_null_reverse_and_mock(self):
        rows = fixture_counts()
        report = summarize_mechanism(rows, "fixture")
        self.assertEqual(report["verdict"]["status"], "supported")
        self.assertEqual(report["comparisons"][0]["delta"], 1)
        self.assertEqual(report["comparisons"][0]["adjusted_p"], 2*report["comparisons"][0]["p"])
        null = summarize_mechanism(fixture_counts((10, 10, 10), (10, 10, 10)), "fixture")
        self.assertEqual(null["verdict"]["status"], "not_detected")
        reverse = summarize_mechanism(fixture_counts((20, 10, 0)), "fixture")
        self.assertEqual(reverse["verdict"]["status"], "supported")
        self.assertEqual(reverse["comparisons"][0]["delta"], -1)
        for r in rows:
            r["source"] = "MOCK_NOT_LLM"
        self.assertEqual(summarize_mechanism(rows, "fixture")["verdict"]["status"], "mock")

    def test_no_success_from_partial_mixed_failed_or_changed_rules(self):
        for change in ("missing", "error", "cancelled", "mixed_model", "mixed_source", "rule", "duplicate", "prompt"):
            rows = fixture_counts()
            if change == "missing":
                rows.pop()
            elif change in ("error", "cancelled"):
                rows[-1]["status"] = change
            elif change == "mixed_model":
                rows[-1]["model_spec"] = {"model": "other"}
            elif change == "mixed_source":
                rows[-1]["source"] = "MOCK_NOT_LLM"
            elif change == "rule":
                rows[-1]["evidence_rule"]["alpha"] = .9
            elif change == "duplicate":
                rows[-1]["repeat"] = 1
            else:
                rows[-1]["prompt_hash"] = "changed"
            with self.subTest(change=change):
                self.assertEqual(summarize_mechanism(rows, "fixture")["verdict"]["status"], "insufficient")
        small = fixture_counts((0, 1, 2), (0, 1, 2), repeats=2)
        self.assertEqual(summarize_mechanism(small, "fixture")["verdict"]["status"], "insufficient")

    def test_unclear_other_retained_and_reviews_do_not_move_primary_result(self):
        rows = fixture_counts()
        rows[0]["machine_coding"] = {"interpretation": "unclear", "action": "other"}
        rows[0]["channels"]["behavior"] = None
        rows[0]["human_review"] = {"coding": {"interpretation": "negative", "action": "avoid"}}
        r = summarize_mechanism(rows, "fixture")["conditions"]["state_none"]
        self.assertEqual(r["complete_n"], 20)
        self.assertEqual(r["interpretation"]["unclear"], .05)
        self.assertEqual(r["negative_rate"], 0)
        self.assertEqual(r["missing_behavior_n"], 1)

    def test_runner_keeps_raw_failed_format_and_enforces_missing_behavior(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "fixture.sqlite3")
            settings = plan(store.design(), request(1, "live"))
            code = json.dumps({"interpretation": "neutral", "action": "avoid",
                               "coding_confidence": .8, "coding_reason": "fixture"})
            with patch("runner.call", side_effect=[("内心想法：我不确定。", {}), (code, {})]):
                result = execute_task(store, store.design(), settings["tasks"][0], settings, "fixture", threading.Event())
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["machine_coding"]["action"], "other")
            with patch("runner.call", return_value=("一段没有通道的回答", {})) as call:
                failed = execute_task(store, store.design(), settings["tasks"][1], settings, "fixture", threading.Event())
            self.assertEqual(call.call_count, 1)
            self.assertEqual(failed["status"], "error")
            self.assertIn("format_error", failed)
            self.assertEqual(Store(store.path).trials()[-1]["narrative"], "一段没有通道的回答")

    def test_full_mock_batch_persist_and_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "fixture.sqlite3")
            manager = JobManager(store)
            job = manager.start({**request(), "concurrency": 3})
            for _ in range(400):
                status = manager.get(job["id"])
                if status["status"] in ("complete", "error", "cancelled"):
                    break
                time.sleep(.01)
            self.assertEqual(status["failed"], 0)
            self.assertEqual(status["completed"], 60)
            rows = Store(store.path).trials()
            result = summarize_mechanism(rows, job["id"])
            self.assertEqual(result["complete_n"], 60)
            self.assertEqual(result["verdict"]["status"], "mock")
            self.assertTrue(all(r["evidence_rule"] == RULE and r["channels"]["thought"] for r in rows))


if __name__ == "__main__":
    unittest.main()
