import csv
import json
import tempfile
import unittest
from pathlib import Path

from rr_v05 import (
    CONTEXTS, HUMAN_RR_COLUMNS, SOCIAL_SCENARIOS, CostGuard, encoding_messages,
    human_distribution, load_human_reference, load_stimuli, ordinal_wasserstein,
    parse_encoding, parse_ratings, participant_split, rating_messages,
)


ROOT = Path(__file__).resolve().parents[1]
STIMULI = ROOT / "private_inputs" / "calm_rr_v42.json"


class RRV05ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not STIMULI.is_file():
            raise unittest.SkipTest("private_inputs/calm_rr_v42.json is local-only and not tracked")
        cls.stimuli = load_stimuli(STIMULI)

    def test_source_shape_order_categories_and_ids(self):
        scenarios = self.stimuli["scenarios"]
        self.assertEqual(len(scenarios), 9)
        self.assertEqual([x["id"] for x in scenarios], ["elevator", "wedding", "job", "noise", "meeting_friend", "lunch", "scrape", "shopping", "blood_test"])
        self.assertEqual(sum(len(x["interpretations"]) for x in scenarios), 36)
        self.assertEqual({x["id"] for x in scenarios if x["category"] == "social"}, set(SOCIAL_SCENARIOS))

    def test_phase_separation_and_all_contexts(self):
        for condition in CONTEXTS:
            first = encoding_messages(self.stimuli, condition)
            first_text = json.dumps(first)
            self.assertNotIn("Very similar", first_text)
            self.assertNotIn("elevator_1", first_text)
            second = rating_messages(self.stimuli, condition, json.dumps({x["id"]: "Yes" for x in self.stimuli["scenarios"]}))
            self.assertIn("Very similar", json.dumps(second))

    def test_strict_parsers(self):
        enc = {x["id"]: ("No" if x["id"] in ("meeting_friend", "scrape", "shopping") else "Yes") for x in self.stimuli["scenarios"]}
        self.assertEqual(len(parse_encoding(json.dumps(enc), self.stimuli)), 9)
        ratings = {entry["item_id"]: (entry["position"] - 1) % 4 + 1 for item in self.stimuli["scenarios"] for entry in item["interpretations"]}
        self.assertEqual(len(parse_ratings(json.dumps(ratings), self.stimuli)), 36)
        ratings.pop(next(iter(ratings)))
        with self.assertRaises(ValueError):
            parse_ratings(json.dumps(ratings), self.stimuli)

    def test_private_deterministic_split_and_555(self):
        self.assertEqual(participant_split("42", "x" * 32), participant_split("42", "x" * 32))
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "rr.csv"
            fields = ["participant_id", "session_only", *HUMAN_RR_COLUMNS]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                row = {name: "3" for name in HUMAN_RR_COLUMNS}
                row.update(participant_id="42", session_only="preTest")
                row[HUMAN_RR_COLUMNS[0]] = "555"
                writer.writerow(row)
            rows = load_human_reference(path, "x" * 32)
            self.assertIsNone(rows[0][HUMAN_RR_COLUMNS[0]])

    def test_ordinal_wasserstein_zero_for_matching_point_mass(self):
        rows = []
        for pid in range(20):
            row = {"participant_id": str(pid), "split": "heldout"}
            row.update({column: 3 for column in HUMAN_RR_COLUMNS})
            rows.append(row)
        human = human_distribution(rows)
        model = {entry["item_id"]: [3] for item in self.stimuli["scenarios"] for entry in item["interpretations"]}
        result = ordinal_wasserstein(model, human, self.stimuli)
        self.assertEqual(result["mean_distance"], 0)
        self.assertEqual(len(result["cells"]), 6)

    def test_cost_guard(self):
        guard = CostGuard(0.01)
        guard.reserve(0.009)
        with self.assertRaises(RuntimeError):
            guard.reserve(0.011)


if __name__ == "__main__":
    unittest.main()
