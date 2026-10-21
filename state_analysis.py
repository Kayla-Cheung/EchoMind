"""Descriptive state induction outcomes and explicitly matched human references."""
import csv
import io
import math
from collections import defaultdict

from state_protocol import PROTOCOL_ID, STATE_LABELS, scenario_hash

INTERPRETATIONS = ("positive", "neutral", "negative", "unclear")
ACTIONS = ("approach", "wait", "avoid", "other")


def parse_benchmark(data, protocol):
    metadata = data.get("metadata", {})
    for key in ("name", "reference", "instrument", "group_rule", "coding_version"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError("请填写数据名称、来源、测量工具、分组依据和编码版本")
    metadata = {key: metadata[key].strip()[:2000] for key in ("name", "reference", "instrument", "group_rule", "coding_version")}
    metadata["same_task_confirmed"] = data.get("metadata", {}).get("same_task_confirmed") is True
    reader = csv.DictReader(io.StringIO(data.get("csv", "").lstrip("\ufeff")))
    required = {"participant_id", "anxiety_score", "anxiety_group", "scenario_id", "interpretation", "action"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("CSV 缺少 participant_id, anxiety_score, anxiety_group, scenario_id, interpretation, action")
    scenarios = {s["id"]: s for s in protocol["scenarios"]}
    seen, participants, rows = set(), {}, []
    for row in reader:
        r = {key: (row.get(key) or "").strip() for key in required}
        if not r["participant_id"] or r["scenario_id"] not in scenarios:
            raise ValueError("参与者为空或情境 ID 不属于此协议")
        if r["anxiety_group"] not in ("none", "mild", "moderate") or r["interpretation"] not in INTERPRETATIONS or r["action"] not in ACTIONS:
            raise ValueError("人类分组或编码类别无效；不自动推断临床阈值")
        score = float(r["anxiety_score"])
        if not math.isfinite(score):
            raise ValueError("焦虑测量值须为有限数字")
        pair = r["participant_id"], r["scenario_id"]
        if pair in seen:
            raise ValueError("同一参与者与情境存在重复行；请先处理重复记录")
        seen.add(pair)
        state = score, r["anxiety_group"]
        if r["participant_id"] in participants and participants[r["participant_id"]] != state:
            raise ValueError("同一参与者的测量值或分组不一致")
        participants[r["participant_id"]] = state
        r["anxiety_score"] = score
        r["scenario_hash"] = scenario_hash(scenarios[r["scenario_id"]])
        rows.append(r)
    if not rows or len(rows) > 50000:
        raise ValueError("人类数据为空或超过 50000 行")
    return {"metadata": metadata, "rows": rows, "participant_n": len(participants),
            "provenance": "用户导入；来源与测量有效性尚未经独立核验"}


def coding(row):
    return (row.get("human_review") or {}).get("coding") or row.get("machine_coding") or {}


def rates(items, human=False):
    complete = items if human else [r for r in items if r.get("status") == "complete"]
    codes = complete if human else [coding(r) for r in complete]
    n = len(codes)
    interp = {key: sum(c.get("interpretation") == key for c in codes) / n if n else None for key in INTERPRETATIONS}
    actions = {key: sum(c.get("action") == key for c in codes) / n if n else None for key in ACTIONS}
    unknown = sum(c.get("interpretation") == "unclear" or c.get("action") == "other" for c in codes)
    return {"attempt_n": len(items), "complete_n": n, "participant_n": len({r.get('participant_id') for r in items}) if human else None,
            "failed_n": 0 if human else sum(r.get("status") == "error" for r in items),
            "cancelled_n": 0 if human else sum(r.get("status") == "cancelled" for r in items),
            "uncodable_n": unknown, "interpretation": interp, "action": actions,
            "negative_rate": interp["negative"], "positive_rate": interp["positive"], "avoid_rate": actions["avoid"]}


def summarize_states(records, source, filters=None, benchmark=None):
    if source not in ("LIVE_LLM_API", "MOCK_NOT_LLM"):
        raise ValueError("来源无效")
    filters = filters or {}
    rows = [r for r in records if r.get("protocol") == PROTOCOL_ID and r.get("source") == source]
    for key in ("batch_id", "scenario_id", "scenario_split", "model", "evaluator_model"):
        if filters.get(key):
            rows = [r for r in rows if r.get(key) == filters[key]]
    grouped = defaultdict(list)
    for r in rows:
        key = (r.get("provider"), r.get("model"), r.get("evaluator_provider"), r.get("evaluator_model"),
               r.get("coder_version"), r.get("protocol_hash"), r.get("design_hash"), r.get("batch_id"))
        grouped[key].append(r)
    groups = []
    for key, items in grouped.items():
        conditions = {c: rates([r for r in items if r["condition"] == c]) for c in STATE_LABELS}
        cells = []
        for condition in STATE_LABELS:
            selected = [r for r in items if r["condition"] == condition]
            for sid in sorted({r["scenario_id"] for r in selected}):
                cell_rows = [r for r in selected if r["scenario_id"] == sid]
                cells.append({"condition": condition, "scenario_id": sid,
                              "scenario_hash": cell_rows[0].get("scenario_hash"),
                              "scenario_kind": cell_rows[0]["scenario_kind"], **rates(cell_rows)})
        deltas = []
        for c in ("state_mild", "state_moderate", "state_nonsocial"):
            for kind in ("social", "non_social"):
                bases = {x["scenario_id"]: x for x in cells if x["condition"] == "state_none" and x["scenario_kind"] == kind and x["complete_n"]}
                matches = [(x, bases[x["scenario_id"]]) for x in cells if x["condition"] == c and x["scenario_kind"] == kind and x["complete_n"] and x["scenario_id"] in bases]
                deltas.append({"condition": c, "scenario_kind": kind, "matched_scenarios": len(matches),
                               "negative_delta": sum(x["negative_rate"]-b["negative_rate"] for x, b in matches)/len(matches) if matches else None,
                               "avoid_delta": sum(x["avoid_rate"]-b["avoid_rate"] for x, b in matches)/len(matches) if matches else None})
        human_matches = []
        allowed = source == "LIVE_LLM_API" and benchmark and benchmark["metadata"]["same_task_confirmed"] and benchmark["metadata"]["coding_version"] == key[4]
        if allowed:
            for cell in cells:
                target = {"state_none": "none", "state_mild": "mild", "state_moderate": "moderate"}.get(cell["condition"])
                hs = [r for r in benchmark["rows"] if r["anxiety_group"] == target and r["scenario_hash"] == cell["scenario_hash"]]
                if hs and cell["complete_n"]:
                    hr = rates(hs, human=True)
                    tv_i = sum(abs(cell["interpretation"][v]-hr["interpretation"][v]) for v in INTERPRETATIONS)/2
                    tv_a = sum(abs(cell["action"][v]-hr["action"][v]) for v in ACTIONS)/2
                    baseline = next((x for x in cells if x["condition"] == "state_baseline" and x["scenario_hash"] == cell["scenario_hash"] and x["complete_n"]), None)
                    baseline_i = sum(abs(baseline["interpretation"][v]-hr["interpretation"][v]) for v in INTERPRETATIONS)/2 if baseline else None
                    baseline_a = sum(abs(baseline["action"][v]-hr["action"][v]) for v in ACTIONS)/2 if baseline else None
                    human_matches.append({"condition": cell["condition"], "scenario_id": cell["scenario_id"],
                        "agent_n": cell["complete_n"], "human_n": hr["participant_n"], "human": hr,
                        "negative_difference": cell["negative_rate"]-hr["negative_rate"],
                        "avoid_difference": cell["avoid_rate"]-hr["avoid_rate"],
                        "interpretation_tv": tv_i, "action_tv": tv_a,
                        "baseline_interpretation_tv": baseline_i, "baseline_action_tv": baseline_a,
                        "interpretation_improvement": baseline_i-tv_i if baseline_i is not None else None,
                        "action_improvement": baseline_a-tv_a if baseline_a is not None else None})
        groups.append({"provider": key[0], "model": key[1], "evaluator_provider": key[2], "evaluator_model": key[3],
                       "coder_version": key[4], "protocol_hash": key[5], "design_hash": key[6], "batch_id": key[7],
                       "conditions": conditions, "cells": cells, "deltas": deltas, "human_matches": human_matches})
    human_status = "尚无人类参照，外部有效性未检验"
    if benchmark:
        human_status = "MOCK 不与人类数据计算拟合" if source == "MOCK_NOT_LLM" else "仅比较相同情境文本与编码版本且已确认可比的单元；导入来源尚未独立核验"
    return {"source": source, "n": len(rows), "groups": groups, "human_status": human_status,
            "note": "比例分母为完成编码的试次，包含 unclear/other；失败单列。差值按共同情境等权。无显著性或替代人类结论。",
            "records": rows}
