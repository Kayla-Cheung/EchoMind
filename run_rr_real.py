"""Run the bounded EchoMind v0.5 REAL DeepSeek pilot (no MOCK mode)."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

from env_config import load_local_keys
from model_client import call, make_spec
from rr_v05 import (
    CONTEXTS, FIXED_TEMPORAL_VARIANT, PROTOCOL_ID, CostGuard, canonical, connect,
    encoding_messages, estimate_peak_cost, expected_rating_ids, human_distribution,
    load_human_reference, load_stimuli, memory_messages, new_id, parse_encoding,
    parse_ratings, rating_messages, sha256_file, sha256_text, usage_cost, utc_now,
)


LIMITATIONS = [
    "Seven repeated model episodes are not seven independent human participants.",
    "The pilot tests a pipeline and provides descriptive ordinal distances; it cannot establish human psychological fidelity.",
    "Context conditions intentionally differ, so pooling them is not an estimate of a single model population.",
    "The source materials are public but the OSF materials node has no explicit reuse license; source item text stays local and untracked.",
    "The original word-fragment click interaction is represented as complete words in a text API and is therefore not an exact UI reproduction.",
    "Interactive context is replayed as fixed prior turns; v0.5 does not add extra model-generated acquisition calls.",
]


def private_salt(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    salt = path.read_text(encoding="utf-8").strip()
    if len(salt) < 32:
        raise ValueError("private split salt is too short")
    return salt


def insert_request(db, batch_id, episode_id, phase, messages, raw, meta, parse_status, error=None):
    usage = meta.get("usage") or {}
    cost = usage_cost(usage)
    db.execute(
        "INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_id("req"), batch_id, episode_id, phase, "deepseek-flash", meta.get("response_model"),
         sha256_text(canonical(messages)), canonical(messages), meta.get("response_id"), raw,
         parse_status, canonical(usage), cost, meta.get("latency_ms"), meta.get("attempts"), utc_now(), error),
    )
    return cost


def run(args):
    if not args.real:
        raise SystemExit("Refusing to run: pass --real explicitly. There is no MOCK batch mode.")
    if args.episodes != 7 or args.repeats != 1:
        raise SystemExit("v0.5 smoke is locked to one episode in each of seven contexts")
    if not 0 < args.max_cost_usd <= 0.05:
        raise SystemExit("--max-cost-usd must be > 0 and <= 0.05")

    load_local_keys(args.env_file)
    if not os.getenv("DEEPSEEK_API_KEY", "").strip():
        raise SystemExit("DEEPSEEK_API_KEY is not configured")
    stimuli = load_stimuli(args.stimuli)
    salt = private_salt(args.split_salt_file)
    humans = load_human_reference(args.human_csv, salt, args.heldout_fraction)
    heldout = human_distribution(humans, "heldout")

    # Preflight all known prompts with a conservative placeholder for the phase-1 answer.
    preflight = 0.0
    for condition in CONTEXTS:
        first = encoding_messages(stimuli, condition)
        second = rating_messages(stimuli, condition, canonical({item["id"]: "Yes" for item in stimuli["scenarios"]}))
        preflight += estimate_peak_cost(first, 800) + estimate_peak_cost(second, 1800)
    if preflight > args.max_cost_usd:
        raise SystemExit(f"Conservative preflight ${preflight:.6f} exceeds hard limit ${args.max_cost_usd:.6f}")

    db = connect(args.db)
    batch_id = new_id("rrv05")
    source_pdf_hash = sha256_file(args.source_pdf)
    human_csv_hash = sha256_file(args.human_csv)
    db.execute(
        "INSERT INTO batches (batch_id,created_at,status,protocol_id,requested_model,contexts_json,stimulus_set_hash,source_pdf_sha256,human_csv_sha256,heldout_fraction,split_salt_sha256,budget_limit_usd,limitations_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, utc_now(), "running", PROTOCOL_ID, "deepseek-flash", canonical(CONTEXTS),
         stimuli["stimulus_set_hash"], source_pdf_hash, human_csv_hash, args.heldout_fraction,
         sha256_text(salt), args.max_cost_usd, canonical(LIMITATIONS)),
    )
    for column, dist in heldout.items():
        db.execute("INSERT INTO human_reference VALUES (?,?,?,?,?)", (batch_id, "heldout", column, dist["n"], canonical(dist["probabilities"])))
    db.commit()

    spec = make_spec({"provider": "deepseek", "model": "deepseek-flash", "thinking": "disabled", "temperature": args.temperature})
    guard = CostGuard(args.max_cost_usd)
    returned_models = set()
    try:
        for condition in CONTEXTS:
            episode_id = new_id("ep")
            first_messages = encoding_messages(stimuli, condition)
            db.execute(
                "INSERT INTO episodes (episode_id,batch_id,condition_id,temporal_variant,status,started_at,encoding_prompt_json) VALUES (?,?,?,?,?,?,?)",
                (episode_id, batch_id, condition, FIXED_TEMPORAL_VARIANT if condition != "none" else "none", "encoding", utc_now(), canonical(first_messages)),
            )
            db.commit()
            try:
                guard.reserve(estimate_peak_cost(first_messages, 800))
                encoding_raw, encoding_meta = call(
                    spec, first_messages, timeout=args.timeout, attempts=2, max_output_tokens=800,
                )
                returned_models.add(encoding_meta.get("response_model") or "unknown")
                try:
                    encoding = parse_encoding(encoding_raw, stimuli)
                    encoding_status = "valid"
                    encoding_error = None
                except Exception as exc:
                    encoding_status, encoding_error = "invalid", str(exc)
                    insert_request(db, batch_id, episode_id, "encoding", first_messages, encoding_raw, encoding_meta, encoding_status, encoding_error)
                    guard.add_usage(encoding_meta.get("usage") or {})
                    raise
                insert_request(db, batch_id, episode_id, "encoding", first_messages, encoding_raw, encoding_meta, encoding_status)
                guard.add_usage(encoding_meta.get("usage") or {})

                second_messages = rating_messages(stimuli, condition, encoding_raw)
                db.execute("UPDATE episodes SET status='rating',encoding_raw=?,encoding_parse_json=?,rating_prompt_json=? WHERE episode_id=?",
                           (encoding_raw, canonical(encoding), canonical(second_messages), episode_id))
                db.commit()
                guard.reserve(estimate_peak_cost(second_messages, 1800))
                rating_raw, rating_meta = call(
                    spec, second_messages, timeout=args.timeout, attempts=2, max_output_tokens=1800,
                )
                returned_models.add(rating_meta.get("response_model") or "unknown")
                try:
                    ratings = parse_ratings(rating_raw, stimuli)
                    rating_status = "valid"
                    rating_error = None
                except Exception as exc:
                    rating_status, rating_error = "invalid", str(exc)
                    insert_request(db, batch_id, episode_id, "rating", second_messages, rating_raw, rating_meta, rating_status, rating_error)
                    guard.add_usage(rating_meta.get("usage") or {})
                    raise
                insert_request(db, batch_id, episode_id, "rating", second_messages, rating_raw, rating_meta, rating_status)
                guard.add_usage(rating_meta.get("usage") or {})

                lookup = {entry["item_id"]: (item, entry) for item in stimuli["scenarios"] for entry in item["interpretations"]}
                for item_id in expected_rating_ids(stimuli):
                    item, entry = lookup[item_id]
                    source_hash = sha256_text(canonical({"scenario": item["scenario"], "rating_stem": item["rating_stem"], "interpretation": entry["text"]}))
                    db.execute("INSERT INTO ratings VALUES (?,?,?,?,?,?,?,?,?)",
                               (batch_id, episode_id, condition, item["id"], item["category"], item_id, entry["type"], ratings[item_id], source_hash))
                db.execute("UPDATE episodes SET status='complete',finished_at=?,rating_raw=?,rating_parse_json=? WHERE episode_id=?",
                           (utc_now(), rating_raw, canonical(ratings), episode_id))
                db.commit()
            except Exception as exc:
                db.execute("UPDATE episodes SET status='failed',finished_at=?,error=? WHERE episode_id=?", (utc_now(), str(exc)[:800], episode_id))
                db.commit()
                raise
        db.execute("UPDATE batches SET status='complete',returned_models_json=?,conservative_cost_usd=? WHERE batch_id=?",
                   (canonical(sorted(returned_models)), guard.spent_usd, batch_id))
        db.commit()
    except Exception as exc:
        db.execute("UPDATE batches SET status='failed',returned_models_json=?,conservative_cost_usd=?,error=? WHERE batch_id=?",
                   (canonical(sorted(returned_models)), guard.spent_usd, str(exc)[:1000], batch_id))
        db.commit()
        raise
    finally:
        db.close()
    return {"batch_id": batch_id, "episodes": 7, "api_calls": 14, "conservative_peak_cost_usd": guard.spent_usd,
            "returned_models": sorted(returned_models), "db": str(Path(args.db).resolve())}


def parser():
    p = argparse.ArgumentParser()
    p.add_argument("--real", action="store_true")
    p.add_argument("--episodes", type=int, default=7)
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-cost-usd", type=float, default=0.05)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--heldout-fraction", type=float, default=0.20)
    p.add_argument("--db", required=True)
    p.add_argument("--stimuli", required=True)
    p.add_argument("--human-csv", required=True)
    p.add_argument("--source-pdf", required=True)
    p.add_argument("--split-salt-file", required=True)
    p.add_argument("--env-file", required=True)
    return p


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f"REAL pilot failed: {exc}", file=sys.stderr)
        raise
