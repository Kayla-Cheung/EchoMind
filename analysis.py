"""Exploratory summaries. MOCK and live records are never pooled."""
from collections import defaultdict

from design import CONDITIONS


def summarize(records, source="LIVE_LLM_API", filters=None):
    filters = filters or {}
    rows = [r for r in records if r.get("source") == source and r.get("status") == "complete"]
    for field in ("profile_id", "model", "scenario_id", "condition", "batch_id",
                  "evaluator_provider", "evaluator_model", "coder_version"):
        if filters.get(field):
            rows = [r for r in rows if r.get(field) == filters[field]]
    def code(r):
        return (r.get("human_review") or {}).get("coding") or r.get("machine_coding") or {}
    def rates(items):
        ni = [r for r in items if code(r).get("interpretation") != "unclear"]
        na = [r for r in items if code(r).get("action") != "other"]
        return {"n": len(items), "interpretation_n": len(ni), "action_n": len(na),
            "negative_rate": sum(code(r).get("interpretation") == "negative" for r in ni) / len(ni) if ni else None,
            "avoid_rate": sum(code(r).get("action") == "avoid" for r in na) / len(na) if na else None}
    by_condition = {c: rates([r for r in rows if r["condition"] == c]) for c in CONDITIONS}
    base = by_condition["baseline"]
    for c, stats in by_condition.items():
        stats["negative_delta_baseline"] = (stats["negative_rate"] - base["negative_rate"]
            if stats["negative_rate"] is not None and base["negative_rate"] is not None else None)
        stats["avoid_delta_baseline"] = (stats["avoid_rate"] - base["avoid_rate"]
            if stats["avoid_rate"] is not None and base["avoid_rate"] is not None else None)
    by_scenario = {sid: {c: rates([r for r in rows if r["scenario_id"] == sid and r["condition"] == c])
                   for c in CONDITIONS} for sid in sorted({r["scenario_id"] for r in rows})}
    repeat_groups = defaultdict(list)
    for r in rows:
        repeat_groups[(r["scenario_id"], r["condition"])].append(r)
    repeat_stability = [{"scenario_id": sid, "condition": c, "n": len(items),
        "interpretation_agreement": max((sum(code(r).get("interpretation") == v for r in items) for v in {code(r).get("interpretation") for r in items}), default=0) / len(items),
        "action_agreement": max((sum(code(r).get("action") == v for r in items) for v in {code(r).get("action") for r in items}), default=0) / len(items)}
        for (sid, c), items in sorted(repeat_groups.items()) if len(items) >= 2]
    by_kind = {kind: {c: rates([r for r in rows if r["scenario_kind"] == kind and r["condition"] == c])
                     for c in CONDITIONS} for kind in ("social", "non_social")}
    return {"source": source, "n": len(rows), "by_condition": by_condition, "by_scenario": by_scenario,
        "repeat_stability": repeat_stability, "by_kind": by_kind,
        "note": "探索性描述；模型重复调用不是独立人类参与者；未做显著性检验。"}


def model_comparison(records, source="LIVE_LLM_API", filters=None):
    """Per-model descriptive outcomes, including failed trials and usage."""
    filters = filters or {}
    rows = [r for r in records if r.get("source") == source]
    for key in ("profile_id", "provider", "model", "scenario_id", "batch_id", "evaluator_model", "evaluator_provider", "coder_version"):
        if filters.get(key):
            rows = [r for r in rows if r.get(key) == filters[key]]
    def coding(r):
        return (r.get("human_review") or {}).get("coding") or r.get("machine_coding") or {}
    def usage(r, kind, field):
        u = (r.get(kind + "_meta") or {}).get("usage") or {}
        return u.get(field, u.get("input_tokens" if field == "prompt_tokens" else "output_tokens", 0)) or 0
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("provider") or "openai", r.get("model") or "unknown")].append(r)
    results = []
    for (provider, model), all_items in sorted(groups.items()):
        by_condition = {}
        for condition in CONDITIONS:
            items = [r for r in all_items if r.get("condition") == condition]
            complete = [r for r in items if r.get("status") == "complete"]
            interp = [r for r in complete if coding(r).get("interpretation") in ("positive", "neutral", "negative")]
            acts = [r for r in complete if coding(r).get("action") in ("approach", "wait", "avoid")]
            by_condition[condition] = {"n": len(items), "valid_n": len(complete),
                "failed_n": len([r for r in items if r.get("status") == "error"]),
                "failure_rate": len([r for r in items if r.get("status") == "error"]) / len(items) if items else None,
                "uncodable_n": len([r for r in complete if coding(r).get("interpretation") == "unclear" or coding(r).get("action") == "other"]),
                "uncodable_rate": len([r for r in complete if coding(r).get("interpretation") == "unclear" or coding(r).get("action") == "other"]) / len(complete) if complete else None,
                "interpretation_n": len(interp), "action_n": len(acts),
                "negative_rate": sum(coding(r).get("interpretation") == "negative" for r in interp) / len(interp) if interp else None,
                "avoid_rate": sum(coding(r).get("action") == "avoid" for r in acts) / len(acts) if acts else None}
        baseline = by_condition["baseline"]
        for stats in by_condition.values():
            stats["negative_delta_baseline"] = stats["negative_rate"] - baseline["negative_rate"] if stats["negative_rate"] is not None and baseline["negative_rate"] is not None else None
            stats["avoid_delta_baseline"] = stats["avoid_rate"] - baseline["avoid_rate"] if stats["avoid_rate"] is not None and baseline["avoid_rate"] is not None else None
        role_tokens = {k: sum(usage(r, "role", k) for r in all_items) for k in ("prompt_tokens", "completion_tokens")}
        coder_tokens = {k: sum(usage(r, "coder", k) for r in all_items) for k in ("prompt_tokens", "completion_tokens")}
        latencies = [(r.get("role_meta") or {}).get("latency_ms") for r in all_items]
        latencies = [x for x in latencies if isinstance(x, (int, float))]
        results.append({"provider": provider, "model": model, "n": len(all_items), "by_condition": by_condition,
            "role_tokens": role_tokens, "coder_tokens": coder_tokens,
            "role_latency_mean_ms": round(sum(latencies) / len(latencies)) if latencies else None,
            "cost_estimate_usd": None, "cost_note": "未配置价格表；请按供应商账单和 Token 用量核算。"})
    return {"source": source, "n": len(rows), "models": results,
        "note": "仅描述 Context 效应；跨模型差异不代表真实人类焦虑拟合。"}
