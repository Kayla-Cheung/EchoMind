"""Reproducible read-only audit of the real database; writes separate evidence files.
Run from any cwd: python tests/recovery_audit.py
Never imports server, loads .env, edits trials, or invokes model APIs.
"""
import csv
import hashlib
import io
import json
import random
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from history import batches, batch_report, export, reject_secrets, canonical
from prompt_registry import BUILTINS, stamped

A = "820cb1f4-daf7-43be-a671-d4a62c43491a"
B = "46c4575c-86d3-4f9a-99fb-1d97bcfffcc3"
MIMO = "cd574596-2b71-441a-b8a9-5d979dd33b6c"


def main():
    before = json.loads((ROOT / "data/recovery-before.json").read_text(encoding="utf-8"))
    database = ROOT / "data/pilot.sqlite3"
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        payloads = db.execute("SELECT id,payload FROM trials ORDER BY id").fetchall()
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    hashes = {rid: hashlib.sha256(raw.encode()).hexdigest() for rid, raw in payloads}
    changed = [rid for rid, value in before["row_hashes"].items() if hashes.get(rid) != value]
    assert not changed, "Original payloads changed: " + repr(changed)
    rows = [json.loads(raw) for _, raw in payloads]
    reject_secrets(rows)
    output = ROOT / "data/research-audit"
    output.mkdir(exist_ok=True)
    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = {"database": str(database), "integrity": integrity, "original_n": before["records"],
                "current_n": len(rows), "unchanged_original_n": len(before["row_hashes"]) - len(changed),
                "payload_sha256": hashlib.sha256("\n".join(raw for _, raw in payloads).encode()).hexdigest(),
                "source_status_counts": {"/".join(k): v for k, v in Counter((r["source"], r["status"]) for r in rows).items()},
                "batches": batches(rows), "schema": tables, "old_exports": {}, "metrics": {}}
    for name, bid in (("A", A), ("B", B), ("MiMo_failed", MIMO)):
        report = batch_report(rows, bid)
        save(name + "-original.json", export(report["records"]))
        evidence["metrics"][name] = {k: v for k, v in report.items() if k != "records"}
    for filename in ("2026-10-21-820cb1f4.json", "2026-10-21-minimax-91eb2e68.json"):
        path = ROOT.parents[1] / "demo_results" / filename
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        old_rows = document["records"]
        current = {r["id"]: r for r in rows}
        equal = sum(canonical(current.get(r["id"])) == canonical(r) for r in old_rows)
        evidence["old_exports"][filename] = {"records": len(old_rows), "identical_to_database": equal}
    evidence["format_descriptives"] = []
    for fmt in ("channels", "free"):
        for condition in ("positive_self", "negative_self", "negative_other", "baseline"):
            cell = [r for r in rows if r.get("batch_id") == B and r["ablation_format"] == fmt and r["condition"] == condition]
            evidence["format_descriptives"].append({"format": fmt, "condition": condition,
                "n": len(cell), "mean_characters": sum(len(r["narrative"]) for r in cell) / len(cell),
                "old_literal_again_hits": sum("又是" in r["narrative"] or "果然又" in r["narrative"] for r in cell),
                "missing_behavior_channel": sum(not (r.get("channels") or {}).get("behavior") for r in cell) if fmt == "channels" else None})
    save("inventory-and-metrics.json", evidence)
    save("all-original-records.json", export(rows))
    for bundle in BUILTINS:
        save(bundle["version"] + ".json", stamped(bundle))
    # Blank independent re-review pack, not invented human annotations.
    review = [r for r in rows if r.get("batch_id") in (A, B) and r["status"] == "complete"]
    random.Random(20261021).shuffle(review)
    mapping, stream = [], io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["blind_id", "scenario", "response", "negative_attribution", "benign_attribution", "negative_affect", "memory_link", "action_list", "evidence_quotes", "uncertainty", "reviewer"])
    for index, row in enumerate(review, 1):
        bid = f"R{index:03d}"
        writer.writerow([bid, row["snapshot"]["scenario"]["situation"], row["narrative"], *([""] * 9)])
        mapping.append({"blind_id": bid, "trial_id": row["id"], "batch_id": row["batch_id"]})
    (output / "blind-review-84.csv").write_text(stream.getvalue(), encoding="utf-8-sig")
    save("review-mapping-do-not-give-to-coders.json", mapping)
    print(json.dumps({"records": len(rows), "batches": len(evidence["batches"]),
                      "unchanged_originals": evidence["unchanged_original_n"], "integrity": integrity,
                      "exports": evidence["old_exports"], "evidence": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
