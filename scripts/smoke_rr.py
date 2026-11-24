"""Exercise public RR code with invented fixtures, never original human materials."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def synthetic_stimuli():
    """Use original structural categories, but entirely invented test-only wording."""
    scenarios = []
    for index in range(9):
        scenario_id = f"synthetic_{index}"
        scenarios.append({
            "id": scenario_id, "title": f"Synthetic software fixture {index}",
            "scenario": f"TEST ONLY: an invented participant encounters fictional marker {index}.",
            "question": "Is this a synthetic software fixture?", "question_answer": "Yes",
            "category": ("social", "physical_health", "other_threat")[index // 3],
            "rating_stem": f"Synthetic meaning comparison {index}",
            "interpretations": [
                {"item_id": f"{scenario_id}_{kind}", "type": kind, "position": position,
                 "text": f"Invented interpretation marker {index} option {kind}."}
                for position, kind in enumerate(("nf", "ns", "pf", "ps"), 1)
            ],
        })
    return {"synthetic": True, "scenarios": scenarios}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", required=True, choices=("v05-human-rr", "rr-isolation"))
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "experiments" / args.experiment))
    import rr_v05 as rr

    isolation = None
    if args.experiment == "rr-isolation":
        import isolation_protocol as isolation

    class PublicRRTests(unittest.TestCase):
        def setUp(self):
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "synthetic.json"
                source.write_text(json.dumps(synthetic_stimuli()), encoding="utf-8")
                self.stimuli = rr.load_stimuli(source)

        def test_encoding_never_contains_rating_options(self):
            for condition in rr.CONTEXTS:
                messages = rr.encoding_messages(self.stimuli, condition)
                text = messages[-1]["content"]
                for story in self.stimuli["scenarios"]:
                    self.assertIn(story["scenario"], text)
                    for option in story["interpretations"]:
                        self.assertNotIn(option["text"], text)
                self.assertNotIn("Very similar", text)

        def test_rating_preserves_encoding_and_rejects_invalid_scale(self):
            raw = json.dumps({s["id"]: "Yes" for s in self.stimuli["scenarios"]})
            encoding = rr.encoding_messages(self.stimuli, "none")
            rating = rr.rating_messages(self.stimuli, "none", raw)
            self.assertEqual(rating[:-2], encoding)
            self.assertEqual(rating[-2], {"role": "assistant", "content": raw})
            answers = {e["item_id"]: 3 for s in self.stimuli["scenarios"] for e in s["interpretations"]}
            self.assertEqual(len(rr.parse_ratings(json.dumps(answers), self.stimuli)), 36)
            key = next(iter(answers))
            for bad in (True, 0, 5, 2.5):
                answers[key] = bad
                with self.assertRaises(ValueError):
                    rr.parse_ratings(json.dumps(answers), self.stimuli)
            answers.pop(key)
            with self.assertRaises(ValueError):
                rr.parse_ratings(json.dumps(answers), self.stimuli)

        def test_known_ordinal_distances_and_missing_cells(self):
            # A point mass at 1 versus 4 has W1=3; an identical mass has W1=0.
            model, reference = {}, {}
            for story in self.stimuli["scenarios"]:
                for option in story["interpretations"]:
                    model[option["item_id"]] = [1, 1]
                    reference[f"{story['id']}_{option['type']}"] = {
                        "n": 2, "probabilities": {str(i): int(i == 4) for i in range(1, 5)}}
            scope = {s["id"] for s in self.stimuli["scenarios"]}
            result = rr.ordinal_wasserstein(model, reference, self.stimuli, scenario_filter=scope)
            self.assertEqual(result["mean_distance"], 3)
            self.assertEqual(len(result["cells"]), 18)
            self.assertIsNone(rr.ordinal_wasserstein({}, reference, self.stimuli, scenario_filter=scope)["mean_distance"])
            for cell in reference.values():
                cell["probabilities"] = {str(i): int(i == 1) for i in range(1, 5)}
            self.assertEqual(rr.ordinal_wasserstein(model, reference, self.stimuli, scenario_filter=scope)["mean_distance"], 0)

        def test_splits_and_isolation_schedule(self):
            self.assertEqual(rr.participant_split("synthetic-person", "test-only-salt"),
                             rr.participant_split("synthetic-person", "test-only-salt"))
            with self.assertRaises(ValueError):
                rr.participant_split("synthetic-person", "")
            if isolation is None:
                return
            cells = isolation.schedule(self.stimuli)
            self.assertEqual(len(cells), 60)
            self.assertEqual(len({c["episode_id"] for c in cells}), 60)
            self.assertEqual(cells, isolation.schedule(self.stimuli))
            expected_ratings = 0
            for cell in cells:
                selected = isolation.select_stimuli(self.stimuli, cell)
                self.assertEqual(len(selected["scenarios"]), 9 if cell["arm"] == "BATCH" else 1)
                raw = json.dumps({s["id"]: "Yes" for s in selected["scenarios"]})
                msg = isolation.messages(self.stimuli, cell, "encoding")
                for story in self.stimuli["scenarios"]:
                    self.assertEqual(story["scenario"] in msg[-1]["content"], story in selected["scenarios"])
                self.assertEqual(isolation.messages(self.stimuli, cell, "rating", raw)[:-2], msg)
                expected_ratings += 4 * len(selected["scenarios"])
            self.assertEqual(expected_ratings, 432)
            self.assertEqual(isolation.w1([1, 0, 0, 0], [0, 0, 0, 1]), 3)

    print(f"{args.experiment}: SYNTHETIC software checks; no human data or model calls", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PublicRRTests))
    return int(not result.wasSuccessful())


if __name__ == "__main__":
    raise SystemExit(main())
