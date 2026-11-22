"""One fixed question, three memory conditions, a frozen exploratory decision rule."""
import math
from collections import Counter

from channels import FORMAT_VERSION, CODER_VERSION
from state_protocol import CORE_STATES, fingerprint
from state_analysis import rates

PROTOCOL_ID = "memory-ratio-v1"
LABELS = {"state_none": "平稳经历", "state_mild": "混合经历", "state_moderate": "不利经历"}
CLAIM = "固定人物、模型和同一问题，仅改变经历条件，会改变回答中的解释或行动比例。"
RULE = {
    "version": "mechanism-evidence-v1",
    "claim": CLAIM,
    "comparison": ["state_moderate", "state_none"],
    "endpoints": ["negative", "avoid"],
    "test": "two-sided Fisher exact; Bonferroni for 2 endpoints",
    "alpha": 0.05,
    "min_repeats": 20,
    "scope": "单批次、单题、单材料版的探索性模型采样；不校正跨批次挑选，不代表人类。",
}


def fisher_exact(a, n_a, b, n_b):
    """Sum hypergeometric tables no more probable than the observed table."""
    if not n_a or not n_b:
        return None
    total, successes = n_a + n_b, a + b
    low, high = max(0, successes - n_b), min(n_a, successes)
    weight = lambda x: math.comb(n_a, x) * math.comb(n_b, successes - x)
    observed = weight(a)
    return min(1.0, sum(weight(x) for x in range(low, high + 1) if weight(x) <= observed)
               / math.comb(total, successes))


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p, z2 = k / n, z * z
    middle = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return [max(0, middle - half), min(1, middle + half)]


def mechanism_batches(records):
    batches = {}
    for r in records:
        if r.get("protocol") != PROTOCOL_ID:
            continue
        batches.setdefault(r["batch_id"], {"id": r["batch_id"], "timestamp": r["timestamp"],
                                          "source": r["source"], "model": r["model"], "n": 0})
        batches[r["batch_id"]]["n"] += 1
    return sorted(batches.values(), key=lambda b: b["timestamp"], reverse=True)


def summarize_mechanism(records, batch_id):
    # No user-selectable subset of rows or favorable repeats enters the verdict.
    rows = [r for r in records if r.get("protocol") == PROTOCOL_ID and r.get("batch_id") == batch_id]
    if not rows:
        raise ValueError("该批次尚无试次记录")
    rows.sort(key=lambda r: r.get("schedule_index", 0))
    first = rows[0]
    request = first.get("snapshot", {}).get("request") or {}
    repeats = request.get("repeats", 0)
    planned = 3 * repeats
    cells = {}
    for condition in CORE_STATES:
        selected = [r for r in rows if r["condition"] == condition]
        # Freeze primary analysis to the blind machine coding; retain human reviews in exports.
        selected = [{**r, "human_review": None} for r in selected]
        complete = [r for r in selected if r["status"] == "complete"]
        counts_i = Counter(r["machine_coding"]["interpretation"] for r in complete)
        counts_a = Counter(r["machine_coding"]["action"] for r in complete)
        cells[condition] = {
            **rates(selected), "interpretation_counts": dict(counts_i), "action_counts": dict(counts_a),
            "negative_ci": wilson(counts_i["negative"], len(complete)),
            "avoid_ci": wilson(counts_a["avoid"], len(complete)),
            "missing_speech_n": sum(not r.get("channels", {}).get("speech") for r in complete),
            "missing_behavior_n": sum(not r.get("channels", {}).get("behavior") for r in complete),
            "format_error_n": sum(bool(r.get("format_error")) for r in selected),
        }
    comparisons = []
    high, low = cells["state_moderate"], cells["state_none"]
    for endpoint, key in (("negative", "interpretation_counts"), ("avoid", "action_counts")):
        a, b = high[key].get(endpoint, 0), low[key].get(endpoint, 0)
        n_a, n_b = high["complete_n"], low["complete_n"]
        p = fisher_exact(a, n_a, b, n_b)
        comparisons.append({"endpoint": endpoint, "counts": [a, n_a, b, n_b],
                            "delta": a / n_a - b / n_b if n_a and n_b else None,
                            "p": p, "adjusted_p": min(1, 2 * p) if p is not None else None})

    blockers = []
    if planned == 0 or len(rows) != planned or any(c["complete_n"] != repeats for c in cells.values()):
        blockers.append("批次尚未全部完成，或存在失败／取消；不按成功子集下结论。")
    if type(repeats) is not int or repeats < RULE["min_repeats"]:
        blockers.append("每组至少完成 20 次，才开启探索性判断；20 次并非功效保证。")
    for key in ("source", "model_spec", "evaluator_spec", "scenario_hash", "induction_variant",
                "protocol_hash", "design_hash", "prompt_version", "coder_version", "evidence_rule"):
        if len({fingerprint(r.get(key)) for r in rows}) != 1:
            blockers.append("批次配置不一致：" + key)
    if any(r.get("output_format") != FORMAT_VERSION or r.get("coder_version") != CODER_VERSION
           or r.get("evidence_rule") != RULE for r in rows):
        blockers.append("输出、编码或判定规则版本不匹配。")
    for c in CORE_STATES:
        group = [r for r in rows if r["condition"] == c]
        if (len({r.get("prompt_hash") for r in group}) != 1
                or sorted(r.get("repeat", 0) for r in group) != list(range(1, repeats + 1))):
            blockers.append(LABELS[c] + "的重复编号或提示不一致。")
    for meta in ("role_meta", "coder_meta"):
        actual = {r.get(meta, {}).get("response_model") for r in rows if r.get(meta, {}).get("response_model")}
        if len(actual) > 1:
            blockers.append("同批次返回了不同模型版本：" + meta)
    source = first["source"]
    if source != "LIVE_LLM_API":
        status, title = "mock", "流程演示 · 尚无模型证据"
        reason = "这些回答与分类来自 MOCK 测试样例，比例差异不检验 claim。"
    elif blockers:
        status, title = "insufficient", "证据不足 · 暂不判断"
        reason = " ".join(dict.fromkeys(blockers))
    elif any(x["adjusted_p"] < RULE["alpha"] for x in comparisons):
        status, title = "supported", "本批次支持经历条件效应"
        reason = "至少一项预先指定的回答比例存在差异；结论限于此模型、此问题和此材料版。需要新批次复现。"
    else:
        status, title = "not_detected", "本批次未检出明确差异"
        reason = "两项指标均未通过预设阈值。保留这个结果；未检出不等于证明没有效应。"
    return {
        "batch_id": batch_id, "source": source, "model": first["model"], "provider": first["provider"],
        "evaluator_model": first["evaluator_model"], "evaluator_provider": first["evaluator_provider"],
        "scenario": first["snapshot"]["scenario"], "variant": first.get("induction_variant"),
        "rule": RULE, "repeats": repeats, "planned_n": planned, "recorded_n": len(rows),
        "complete_n": sum(c["complete_n"] for c in cells.values()),
        "conditions": cells, "comparisons": comparisons,
        "verdict": {"status": status, "title": title, "reason": reason, "blockers": blockers},
        "records": rows,
    }
