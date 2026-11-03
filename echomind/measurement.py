"""Source x valence pilot; frozen inputs and multiaxis, descriptive measurement.

No legacy recoding, inferred anxiety states, or significance verdicts.
"""
import copy
import csv
import io
import json
import random
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .history import digest
from .prompt_registry import BUILTINS, MULTIAXIS_SCHEMA, preview, stamped, validate_bundle, validate_multiaxis

PROTOCOL_ID = "memory-source-v2"
MATERIAL_VERSION = "source-materials-v1"
CONDITIONS = {
    "self_benign": "自己 · 平稳经历", "self_adverse": "自己 · 不利经历",
    "other_benign": "他人 · 平稳经历", "other_adverse": "他人 · 不利经历",
}
SCENARIOS = [
    {"id": "V2S01", "kind": "social", "distance": "near", "title": "讨论中的停顿",
     "situation": "你在课程讨论中提出一个建议。两位组员看了一眼笔记，短暂沉默，随后主持人说先看下一项。你还没有听到他们对建议的评价。"},
    {"id": "V2S02", "kind": "social", "distance": "near", "title": "活动安排未定",
     "situation": "你向活动组织者询问自己负责哪一项任务。对方说安排还要调整，稍后再告诉你。你发现已有几位同学拿到了任务表，但不知道分配顺序。"},
    {"id": "V2S03", "kind": "social", "distance": "far", "title": "餐桌旁的位置",
     "situation": "你端着餐盘走向两位认识的同学。他们把旁边椅子上的包拿了起来，其中一人看向另一张桌子。此时你还没有开口。"},
    {"id": "V2S04", "kind": "social", "distance": "far", "title": "走廊里的谈话",
     "situation": "你经过走廊时，几位熟悉的同学刚好停下交谈，其中一人向你点头，随后他们看了一眼墙上的时间表。你没有听到刚才的谈话内容。"},
]
MATERIALS = [
    {"id": "M1", "title": "课程与活动", "benign":
     "上个月，该学生参加课程分工时提出了一个建议。组员讨论后采用了其中一部分。\n上周，该学生询问活动的集合安排。组织者回复了时间，并把安排表发给了该学生。",
     "adverse": "上个月，该学生参加课程分工时提出了一个建议。组员讨论后没有采用其中的内容。\n上周，该学生询问活动的集合安排。组织者没有回复，也没有把安排表发给该学生。"},
    {"id": "M2", "title": "排班与资料", "benign":
     "上个月，该学生和同学商量值班时间。其他人听取了该学生的时间要求，分配了合适的班次。\n上周，该学生请求借用一份课堂资料。同学同意分享，并在约定的时间发来了资料。",
     "adverse": "上个月，该学生和同学商量值班时间。其他人没有听取该学生的时间要求，分配了冲突的班次。\n上周，该学生请求借用一份课堂资料。同学拒绝分享，也没有在约定的时间发来资料。"},
]
RULE = {
    "version": "source-descriptive-v1",
    "primary": "明确提出不利归因；与非不利解释可同时存在。",
    "denominator": "所有非空角色回答；编码失败或 uncertain 保留为未知。另报未返回回答与未发出的任务。",
    "contrast": "D=(self_adverse-self_benign)-(other_adverse-other_benign)",
    "uncertainty": "区间是未知标签的上下界，不是置信区间。D 点值仅在完整、无失败且四格标签均可判断时提供。",
    "scope": "按模型、编码器、提示版本、材料和情境分层；不做显著性或焦虑模拟成功判定。",
    "validation": "人工编写材料及近/远分类均未独立验证；A/B 同时改变测量要求，不是纯排版消融；全部题为开发材料，无已验证保留集。",
}


def _select(ids, available, label, maximum):
    if not isinstance(ids, list) or not ids or len(ids) > maximum or any(not isinstance(x, str) for x in ids) or len(set(ids)) != len(ids):
        raise ValueError(label + "选择无效或重复")
    lookup = {x["id"]: x for x in available}
    if any(x not in lookup for x in ids):
        raise ValueError("未知" + label)
    return [copy.deepcopy(lookup[x]) for x in ids]


def build_tasks(design, request, models, repeats, bundles=None):
    if len(models) != 1:
        raise ValueError("来源对照每批固定一个角色模型；跨模型请分别运行")
    if request.get("conditions", list(CONDITIONS)) != list(CONDITIONS):
        raise ValueError("来源对照必须包含全部四个条件")
    selected_scenes = _select(request.get("scenario_ids", ["V2S01"]), SCENARIOS, "情境", 4)
    selected_materials = _select(request.get("material_ids", ["M1"]), MATERIALS, "材料", 2)
    versions = request.get("prompt_versions", [x["version"] for x in BUILTINS])
    choices = [{**x, "id": x["version"]} for x in (bundles or [stamped(x) for x in BUILTINS])]
    selected = _select(versions, choices, "提示版本", 2)
    for bundle in selected:
        bundle.pop("id")
        validate_bundle(bundle)
    if len({digest([x["coder_version"], x["coder_system"], x["coder_user"]]) for x in selected}) != 1:
        raise ValueError("同一来源对照批次必须使用相同编码规则；不同 coder 请分批")
    identity = copy.deepcopy(design["identity"])
    config = {"protocol": PROTOCOL_ID, "material_version": MATERIAL_VERSION, "identity": identity,
              "scenarios": selected_scenes, "materials": selected_materials, "bundles": selected,
              "rule": copy.deepcopy(RULE), "coding_schema": copy.deepcopy(MULTIAXIS_SCHEMA),
              "conditions": copy.deepcopy(CONDITIONS), "repeats": repeats}
    tasks = []
    for scene in selected_scenes:
        for material in selected_materials:
            for bundle in selected:
                for condition in CONDITIONS:
                    owner, valence = condition.split("_")
                    for repeat in range(1, repeats + 1):
                        tasks.append({"condition": condition, "scenario": scene, "material_id": material["id"],
                                      "memory_source": owner, "memory_valence": valence, "bundle": bundle,
                                      "owner_text": identity["name"] + "本人" if owner == "self" else "另一位同龄学生",
                                      "events": material[valence], "repeat": repeat, "model_spec": models[0],
                                      "memories": [{"id": material["id"], "text": material[valence], "synthetic": True}]})
    return tasks, config


def render(task, identity, response="尚无回答；实际编码时仅替换此处为本条原文"):
    return preview(task["bundle"], identity["name"], identity.get("description", "普通大学生"),
                   task["scenario"]["situation"], task["owner_text"], task["events"], response)


def preview_plan(settings):
    seen, examples = set(), []
    for task in sorted(settings["tasks"], key=lambda t: (t["scenario"]["id"], t["material_id"], t["bundle"]["version"], t["condition"])):
        key = (task["scenario"]["id"], task["material_id"], task["bundle"]["version"], task["condition"])
        if key in seen:
            continue
        seen.add(key)
        examples.append({"scenario_id": key[0], "material_id": key[1], "version": key[2], "condition": key[3],
                         **render(task, settings["measurement_config"]["identity"])})
    return {"preview_hash": settings["preview_hash"], "role_calls": settings["calls"],
            "coding_calls": settings["coding_calls"], "mode": settings["mode"],
            "config": settings["measurement_config"], "examples": examples,
            "notice": "仅预览，无模型调用；传输重试另计。配置改变后须重新预览。"}


def mock_result(task):
    # Same text and codes across all four conditions and both formats for each repeat.
    # This verifies measurement; it must not manufacture a predicted condition effect.
    texts = ["我暂时不知道发生了什么。我先等一会儿。", "也许对方正忙，也许对方不想理我。我晚点询问一下。",
             "我认为对方在排斥我。我决定现在不再联系对方。"]
    response = texts[(task["repeat"] - 1) % len(texts)]
    coding = {x: {"value": "absent", "evidence": []} for x in
              ("negative_attribution", "benign_attribution", "negative_affect", "explicit_memory_link")}
    coding.update(negative_commitment="none", negative_target=[], actions=[], action_observability="explicit", uncertainty_note="MOCK 固定样例，不是模型或人类证据")
    if task["repeat"] % 3 == 2:
        coding["negative_attribution"] = {"value": "present", "evidence": ["也许对方不想理我"]}
        coding["benign_attribution"] = {"value": "present", "evidence": ["也许对方正忙"]}
        coding.update(negative_commitment="possible", negative_target=["other"])
        action = ("contact", "later", "我晚点询问一下")
    elif task["repeat"] % 3 == 0:
        coding["negative_attribution"] = {"value": "present", "evidence": ["我认为对方在排斥我"]}
        coding.update(negative_commitment="endorsed", negative_target=["other"])
        action = ("withdraw", "now", "我决定现在不再联系对方")
    else:
        action = ("wait", "now", "我先等一会儿")
    coding["actions"] = [{"kind": action[0], "timing": action[1], "commitment": "decided", "evidence": [action[2]]}]
    validate_multiaxis(coding, response)
    return response, coding


def execute_task(store, task, settings, batch_id, cancelled, caller):
    config = settings["measurement_config"]
    prompts = render(task, config["identity"])
    role_spec, coder_spec = task["model_spec"], settings["evaluator"]
    record = {"id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), "batch_id": batch_id,
              "source": "MOCK_NOT_LLM" if settings["mode"] == "mock" else "LIVE_LLM_API", "status": "running",
              "protocol": PROTOCOL_ID, "condition": task["condition"], "repeat": task["repeat"],
              "scenario_id": task["scenario"]["id"], "scenario_kind": "social", "scenario_hash": digest(task["scenario"]),
              "memory_source": task["memory_source"], "memory_valence": task["memory_valence"], "material_id": task["material_id"],
              "output_format": task["bundle"]["version"], "prompt_version": task["bundle"]["version"],
              "bundle_hash": prompts["bundle_hash"], "prompt_hash": prompts["prompt_hash"], "role_messages": prompts["role_messages"],
              "coder_version": prompts["coder_version"], "coding_schema": "multiaxis-v3", "machine_coding": None,
              "provider": role_spec.provider, "model": role_spec.model, "model_spec": role_spec.public(),
              "evaluator_provider": coder_spec.provider, "evaluator_model": coder_spec.model, "evaluator_spec": coder_spec.public(),
              "model_parameters": {**role_spec.public(), "timeout": settings["timeout"]},
              "schedule_index": task["schedule_index"], "protocol_hash": digest(config), "evidence_rule": config["rule"],
              "snapshot": {"measurement": copy.deepcopy(config), "scenario": task["scenario"], "memories": task["memories"],
                           "request": copy.deepcopy(settings["request_snapshot"]), "order_seed": settings["order_seed"],
                           "preview_hash": settings["preview_hash"]}}
    store.add_trial(record)
    try:
        if cancelled.is_set():
            record["status"] = "cancelled"
            return record
        if settings["mode"] == "mock":
            response, coding = mock_result(task)
            role_meta = {"mock": True}
        else:
            response, role_meta = caller(role_spec, prompts["role_messages"], timeout=settings["timeout"])
        record.update(narrative=response, role_meta=role_meta)
        store.update_trial(record)
        if not isinstance(response, str) or not response.strip():
            raise ValueError("角色回答为空；不编码为无负面归因")
        prompts = render(task, config["identity"], response)
        record["evaluator_messages"] = prompts["evaluator_messages"]
        store.update_trial(record)
        if cancelled.is_set():
            record["status"] = "cancelled"
            return record
        if settings["mode"] == "mock":
            raw, meta = json.dumps(coding, ensure_ascii=False), {"mock": True}
        else:
            raw, meta = caller(coder_spec, prompts["evaluator_messages"], evaluator=True, timeout=settings["timeout"], coding_schema=config["coding_schema"])
        record.update(evaluator_raw=raw, coder_meta=meta)
        store.update_trial(record)
        coding = validate_multiaxis(json.loads(raw), response)
        record.update(machine_coding=coding, status="complete")
    except Exception as exc:
        record.update(status="error", error=str(exc)[:600], error_meta=getattr(exc, "meta", {"kind": "validation_or_runtime"}))
    finally:
        store.update_trial(record)
    return record


def summarize(records, batch_id, job=None):
    rows = [r for r in records if r.get("batch_id") == batch_id]
    if not rows or any(r.get("protocol") != PROTOCOL_ID for r in rows):
        raise ValueError("请选择完整的来源对照 v2 批次；不混合旧协议")
    groups = defaultdict(list)
    for row in rows:
        # Isolate sources, parameters, measurement rules and materials even on imported batches.
        key = (row.get("source"), row.get("model"), row.get("evaluator_model"), row.get("coder_version"),
               row.get("output_format"), row.get("material_id"), row.get("scenario_id"),
               digest([row.get("model_spec"), row.get("evaluator_spec"), row.get("protocol_hash"), row.get("bundle_hash")]))
        groups[key].append(row)
    strata = []
    for key, subset in groups.items():
        cells = []
        for condition in CONDITIONS:
            cell = [r for r in subset if r.get("condition") == condition]
            responses = [r for r in cell if isinstance(r.get("narrative"), str) and r["narrative"].strip()]
            codes = []
            for row in responses:
                if row.get("status") != "complete":
                    continue
                try:
                    codes.append(validate_multiaxis(row.get("machine_coding"), row["narrative"]))
                except (ValueError, TypeError):
                    pass
            negative = Counter(c["negative_attribution"]["value"] for c in codes)
            n, present, known = len(responses), negative["present"], negative["present"] + negative["absent"]
            unknown = n - known
            expected = (subset[0].get("snapshot", {}).get("measurement") or {}).get("repeats")
            complete = isinstance(expected, int) and expected > 0 and len(cell) == expected and len(codes) == expected and {r.get("repeat") for r in cell} == set(range(1, expected + 1))
            cells.append({"condition": condition, "label": CONDITIONS[condition], "recorded": len(cell), "expected": expected,
                          "response_n": n, "coded_n": len(codes), "negative_present": present, "negative_absent": negative["absent"],
                          "negative_unknown": unknown, "negative_bounds": [present / n, (present + unknown) / n] if n else None,
                          "known_rate": present / known if known else None, "complete": complete,
                          "missing_response": len(cell) - n, "error_n": sum(r.get("status") == "error" for r in cell),
                          "benign_present": sum(c["benign_attribution"]["value"] == "present" for c in codes),
                          "both_present": sum(c["negative_attribution"]["value"] == c["benign_attribution"]["value"] == "present" for c in codes),
                          "memory_link_present": sum(c["explicit_memory_link"]["value"] == "present" for c in codes),
                          "negative_affect_present": sum(c["negative_affect"]["value"] == "present" for c in codes),
                          "immediate_withdraw": sum(any(a["kind"] == "withdraw" and a["timing"] == "now" and a["commitment"] in ("done", "decided") for a in c["actions"]) for c in codes),
                          "conditional_withdraw": sum(any(a["kind"] == "withdraw" and a["timing"] == "conditional" for a in c["actions"]) for c in codes),
                          "action_explicit": sum(c["action_observability"] == "explicit" for c in codes)})
        by = {c["condition"]: c for c in cells}
        ready = all(c["complete"] and c["negative_unknown"] == 0 for c in cells)
        d = (by["self_adverse"]["known_rate"] - by["self_benign"]["known_rate"] - by["other_adverse"]["known_rate"] + by["other_benign"]["known_rate"]) if ready else None
        strata.append({**dict(zip(("source", "model", "evaluator_model", "coder_version", "output_format", "material_id", "scenario_id", "configuration_hash"), key)),
                       "cells": cells, "source_interaction": d,
                       "interaction_note": "完整四格的描述性 D；不是心理机制或显著性结论" if ready else "四格不完整、有失败或未知标签；不计算 D 点值"})
    strata.sort(key=lambda s: tuple(str(s.get(k) or "") for k in ("scenario_id", "material_id", "output_format", "configuration_hash")))
    return {"protocol": PROTOCOL_ID, "batch_id": batch_id, "records": rows, "strata": strata,
            "job": job, "recorded": len(rows), "sources": sorted({r["source"] for r in rows}),
            "rule": RULE, "evidence_status": "MOCK 仅验证流程，不是研究证据" if any(r["source"] != "LIVE_LLM_API" for r in rows) else "探索性结果；编码与材料尚未人工校准，不判定 claim 成立"}


def review_pack(records, batch_id):
    """Primary-endpoint human review sheet. No original labels or conditions.

    Stable opaque IDs permit joining two separately shuffled sheets later.
    The researcher keeps the separate key; this is metadata masking, not access control.
    """
    rows = [r for r in records if r.get("batch_id") == batch_id and isinstance(r.get("narrative"), str) and r["narrative"].strip()]
    if not rows:
        raise ValueError("该批次没有可供复核的原回答")
    random.SystemRandom().shuffle(rows)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["case_id", "scenario", "response", "reviewer_id", "negative_attribution", "negative_evidence", "benign_attribution", "benign_evidence", "note"])
    key = []
    for row in rows:
        case_id = digest(["primary-review-v1", row["id"]])[:24]
        scene = (row.get("snapshot") or {}).get("scenario") or {}
        writer.writerow([case_id, scene.get("situation", "未保存情境，需标记无法判断"), row["narrative"], "", "", "", "", "", ""])
        key.append({"case_id": case_id, "trial_id": row["id"], "batch_id": row.get("batch_id"), "source": row.get("source")})
    return {"csv": "\ufeff" + buf.getvalue(), "key": key, "codebook": "blind-multiaxis-v3.0 的 negative_attribution / benign_attribution 两维；事后复核，不改旧标签"}
