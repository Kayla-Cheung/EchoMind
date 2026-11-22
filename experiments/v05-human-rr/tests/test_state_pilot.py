import copy
import json
import tempfile
import time
import unittest
from pathlib import Path

from design import initial_design, CODER_VERSION
from prompts import role_messages, evaluator_messages
from runner import plan, JobManager
from storage import Store
from state_protocol import default_protocol, PROTOCOL_ID, CORE_STATES, scenario_hash
from state_analysis import parse_benchmark, summarize_states


def human_payload():
    return {"metadata": {"name": "synthetic test fixture", "reference": "test only; not human evidence",
            "instrument": "fixture", "group_rule": "fixture", "coding_version": CODER_VERSION, "same_task_confirmed": True},
            "csv": "participant_id,anxiety_score,anxiety_group,scenario_id,interpretation,action\nP1,0,none,S01,positive,wait\nP2,1,none,S01,negative,avoid\n"}


class StatePilotTests(unittest.TestCase):
    def test_clean_context_and_blind_coder_across_targets(self):
        d = initial_design()
        config = default_protocol(d)
        p = plan(d, {"protocol": PROTOCOL_ID, "conditions": list(CORE_STATES), "scenario_ids": ["S01"], "variants": ["A", "B", "C"]}, config)
        self.assertEqual(len(p["tasks"]), 9)
        self.assertEqual({t["schedule_index"] for t in p["tasks"]}, set(range(1, 10)))
        prompts = [role_messages(d, t["scenario"], t["memories"])["messages"] for t in p["tasks"]]
        self.assertEqual(len({x[0]["content"] for x in prompts}), 1)
        self.assertTrue(all(len(x) == 2 for x in prompts))
        for messages in prompts:
            for forbidden in (*CORE_STATES, "无焦虑", "目标轻度", "目标中度", "anxiety_score"):
                self.assertNotIn(forbidden, json.dumps(messages, ensure_ascii=False))
        coder = evaluator_messages(config["scenarios"][0], "我先等一会儿。", d["coding_rules"])
        self.assertNotIn("state_", json.dumps(coder))
        with self.assertRaises(ValueError):
            role_messages(d, config["scenarios"][0], [{"text": "我现在处于中度焦虑。"}])

    def test_persist_snapshot_and_keep_legacy_record(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "state.sqlite3")
            legacy = {"id": "old", "timestamp": "2020", "status": "complete", "source": "MOCK_NOT_LLM", "narrative": "original"}
            store.add_trial(legacy)
            manager = JobManager(store)
            job = manager.start({"protocol": PROTOCOL_ID, "mode": "mock", "scenario_ids": ["S01"], "concurrency": 2})
            for _ in range(200):
                status = manager.get(job["id"])
                if status["status"] in ("complete", "error"):
                    break
                time.sleep(.01)
            self.assertEqual(status["status"], "complete")
            rows = store.trials()
            self.assertEqual(rows[0], legacy)
            self.assertEqual(len(rows), 4)
            old_snapshot = copy.deepcopy(rows[1]["snapshot"])
            protocol = store.state_protocol()
            protocol["profiles"][0]["memories"]["A"][0] = "上个月我参加一次整理活动，其他人递给我需要用的材料，随后大家一起完成了工作。"
            store.save_state_protocol(protocol)
            reopened = Store(store.path)
            self.assertEqual(reopened.trials()[1]["snapshot"], old_snapshot)
            self.assertEqual(reopened.state_protocol(), protocol)
            self.assertEqual({r["condition"] for r in rows[1:]}, set(CORE_STATES))
            self.assertTrue(all(r["snapshot"]["state_protocol"] and r["snapshot"]["order_seed"] is not None for r in rows[1:]))

    def test_human_import_validates_duplicates_and_atomicity(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "human.sqlite3")
            payload = human_payload()
            result = store.import_state_benchmark(payload)
            self.assertEqual(result["participant_n"], 2)
            with self.assertRaises(ValueError):
                store.import_state_benchmark(payload)
            bad = copy.deepcopy(payload)
            bad["csv"] += "P1,0,none,S01,negative,avoid\n"
            with self.assertRaises(ValueError):
                store.import_state_benchmark(bad)
            self.assertEqual(len(Store(store.path).state_benchmarks()), 1)
            self.assertEqual(store.human_count(), 0)

    def test_full_distribution_denominators_and_human_gates(self):
        config = default_protocol(initial_design())
        digest = scenario_hash(config["scenarios"][0])
        base = {"protocol": PROTOCOL_ID, "source": "LIVE_LLM_API", "condition": "state_none", "status": "complete",
                "model": "fixture", "provider": "openai", "evaluator_model": "coder", "evaluator_provider": "openai",
                "coder_version": CODER_VERSION, "scenario_id": "S01", "scenario_hash": digest, "scenario_kind": "social"}
        rows = [{**base, "machine_coding": {"interpretation": "negative", "action": "avoid"}},
                {**base, "machine_coding": {"interpretation": "unclear", "action": "other"}},
                {**base, "status": "error"}]
        benchmark = parse_benchmark(human_payload(), config)
        report = summarize_states(rows, "LIVE_LLM_API", benchmark=benchmark)
        x = report["groups"][0]["conditions"]["state_none"]
        self.assertEqual(x["negative_rate"], .5)
        self.assertEqual((x["failed_n"], x["uncodable_n"], x["complete_n"]), (1, 1, 2))
        match = report["groups"][0]["human_matches"][0]
        self.assertEqual(match["interpretation_tv"], .5)
        self.assertEqual(match["human_n"], 2)
        self.assertIsNone(match["interpretation_improvement"])
        with_baseline = rows + [{**base, "condition": "state_baseline", "machine_coding": {"interpretation": "neutral", "action": "wait"}}]
        compared = summarize_states(with_baseline, "LIVE_LLM_API", benchmark=benchmark)["groups"][0]["human_matches"][0]
        self.assertEqual(compared["interpretation_improvement"], .5)
        wrong_version = copy.deepcopy(benchmark)
        wrong_version["metadata"]["coding_version"] = "unknown"
        self.assertFalse(summarize_states(rows, "LIVE_LLM_API", benchmark=wrong_version)["groups"][0]["human_matches"])
        wrong_scene = [{**r, "scenario_hash": "different-text"} for r in rows]
        self.assertFalse(summarize_states(wrong_scene, "LIVE_LLM_API", benchmark=benchmark)["groups"][0]["human_matches"])
        mock = [{**r, "source": "MOCK_NOT_LLM"} for r in rows]
        self.assertFalse(summarize_states(mock, "MOCK_NOT_LLM", benchmark=benchmark)["groups"][0]["human_matches"])
        benchmark["metadata"]["same_task_confirmed"] = False
        self.assertFalse(summarize_states(rows, "LIVE_LLM_API", benchmark=benchmark)["groups"][0]["human_matches"])
        self.assertEqual(summarize_states(mock, "LIVE_LLM_API")["n"], 0)


if __name__ == "__main__":
    unittest.main()
