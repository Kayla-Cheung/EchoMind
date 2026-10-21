"""Read-only historical views and transactional, append-only JSON recovery.

No protocol migration or retrospective recoding takes place here.
"""
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

SHANGHAI = timezone(timedelta(hours=8))
LEGACY = "legacy-unspecified"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def batch_key(row):
    return row.get("batch_id") or "unbatched:" + row["id"]


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("时间必须包含时区；不推测旧记录的时区")
    return parsed


def batches(records, filters=None):
    filters = filters or {}
    grouped = defaultdict(list)
    for row in records:
        grouped[batch_key(row)].append(row)
    result = []
    for bid, rows in grouped.items():
        counts = Counter(r.get("status", "unknown") for r in rows)
        item = {"id": bid, "timestamp": min(r["timestamp"] for r in rows), "n": len(rows),
                "statuses": dict(counts), "complete": counts["complete"], "error": counts["error"]}
        for name in ("protocol", "model", "source", "coder_version"):
            item[name + "s"] = sorted({str(r.get(name) or (LEGACY if name == "protocol" else "unknown")) for r in rows})
        item["date"] = timestamp(item["timestamp"]).astimezone(SHANGHAI).date().isoformat()
        if any(filters.get(k) and filters[k] not in item[k + "s"] for k in ("protocol", "model", "source")):
            continue
        if filters.get("status") and filters["status"] not in counts:
            continue
        if filters.get("from") and item["date"] < filters["from"]:
            continue
        if filters.get("to") and item["date"] > filters["to"]:
            continue
        result.append(item)
    return sorted(result, key=lambda r: timestamp(r["timestamp"]), reverse=True)


def select_records(records, filters=None):
    filters = filters or {}
    ids = {r["id"] for r in batches(records, filters)}
    if filters.get("batch_id"):
        ids &= {filters["batch_id"]}
    return [r for r in records if batch_key(r) in ids]


def batch_report(records, batch_id):
    rows = [r for r in records if batch_key(r) == batch_id]
    if not rows:
        raise ValueError("没有对应批次")
    # Each cell retains protocol, source, measurement version and configuration.
    # Never pool model variants or settings just because their display names match.
    keys = ("protocol", "source", "model", "evaluator_model", "coder_version", "scenario_id",
            "condition", "ablation_format", "output_format", "induction_variant", "prompt_hash")
    groups = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(k) or (LEGACY if k == "protocol" else "unknown")) for k in keys)
        key += (digest([row.get("model_spec"), row.get("evaluator_spec"), row.get("model_parameters")]),)
        groups[key].append(row)
    cells = []
    for key, subset in groups.items():
        valid = [r for r in subset if r.get("status") == "complete" and isinstance(r.get("machine_coding"), dict)
                 and r["machine_coding"].get("interpretation") in ("positive", "neutral", "negative", "unclear")
                 and r["machine_coding"].get("action") in ("approach", "wait", "avoid", "other")]
        inter = Counter(r["machine_coding"]["interpretation"] for r in valid)
        actions = Counter(r["machine_coding"]["action"] for r in valid)
        cells.append({**dict(zip(keys, key)), "configuration_hash": key[-1], "recorded": len(subset),
                      "coded_n": len(valid), "excluded": len(subset) - len(valid),
                      "interpretations": dict(inter), "actions": dict(actions),
                      "negative_rate": inter["negative"] / len(valid) if valid else None,
                      "avoid_rate": actions["avoid"] / len(valid) if valid else None})
    protocols = {r.get("protocol") for r in rows}
    original, original_error = None, None
    # Frozen legacy report logic, only when the WHOLE batch has one known protocol.
    try:
        if protocols == {"memory-ratio-v1"}:
            from mechanism import summarize_mechanism
            original = summarize_mechanism(rows, batch_id)
        elif protocols == {"memory-ablation-v1"}:
            from ablation import summarize_ablation
            original = summarize_ablation(rows, batch_id)
        if original:
            original = {k: v for k, v in original.items() if k != "records"}
    except (ValueError, KeyError, TypeError) as exc:
        original_error = "旧报告所需字段不足；原记录仍完整可见：" + str(exc)
    return {"batch": batches(rows)[0], "cells": cells, "records": rows,
            "original_report": original, "original_report_error": original_error,
            "measurement_note": "此历史视图仅展示原 machine_coding；分母为 complete 且具备有效旧分类的记录，包含 unclear/other。失败、取消、运行中和缺失编码单列。不同协议、来源、编码版本、配置和格式分格，不合并检验。旧版 legacy/state 页面可能采用人工复核或排除 unclear/other；请以原协议报告说明为准。"}


def export(records):
    return {"schema": "sos-history-v1", "exported_at": datetime.now(timezone.utc).isoformat(),
            "records_sha256": digest(records), "records": records,
            "notice": "原始记录逐字段保留；缺失字段不补造。MOCK 和失败记录不是有效模型证据。"}


def reject_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().replace("-", "_") in ("api_key", "apikey", "authorization", "access_token", "secret") or key.lower().endswith("_api_key"):
                raise ValueError("拒绝含凭据字段的导入；请在副本中移除凭据后重试")
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)


def parse_import_json(text):
    if not isinstance(text, str):
        raise ValueError("document_json 必须为原始 JSON 文字")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("JSON 包含重复字段；请检查原文件")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("JSON 数字必须有限")))


def import_records(store, document, *, commit=False, expected_digest=None):
    rows = document.get("records") if isinstance(document, dict) else document
    if not isinstance(rows, list) or not rows or len(rows) > 10000:
        raise ValueError("需要非空 records 数组（最多 10000 条）；不接受只有汇总数字的文件")
    reject_secrets(rows)
    content_hash = digest(rows)
    if isinstance(document, dict) and document.get("records_sha256") not in (None, content_hash):
        raise ValueError("导出文件校验失败")
    if commit and expected_digest != content_hash:
        raise ValueError("必须先预览同一文件，提交其 digest")
    unique, conflicts = {}, []
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in ("id", "timestamp", "source", "status")):
            raise ValueError("每条记录须有原始 id、timestamp、source、status；不会自动补造")
        timestamp(row["timestamp"])
        if row.get("batch_id") is not None and not isinstance(row["batch_id"], str):
            raise ValueError("batch_id 必须为文字或 null")
        for name in ("protocol", "model", "coder_version", "scenario_id"):
            if row.get(name) is not None and not isinstance(row[name], str):
                raise ValueError(name + " 必须为文字")
        if row["id"] in unique and canonical(unique[row["id"]]) != canonical(row):
            conflicts.append(row["id"])
        unique[row["id"]] = row
    with store.lock:
        existing = {r["id"]: r for r in store.trials()}
        for rid, row in unique.items():
            if rid in existing and canonical(existing[rid]) != canonical(row):
                conflicts.append(rid)
        new = [r for rid, r in unique.items() if rid not in existing]
        result = {"digest": content_hash, "input_n": len(rows), "new_n": len(new),
                  "duplicate_n": len(rows) - len(new), "conflicts": sorted(set(conflicts)),
                  "imported": 0, "backup": None}
        if commit:
            if conflicts:
                raise ValueError("存在同 ID 不同内容的冲突；整份文件未写入")
            if new:
                result["backup"] = store.backup()
                with store.connection() as db:
                    db.executemany("INSERT INTO trials VALUES (?,?,?,?,?,?)", [
                        (r["id"], r["timestamp"], r.get("batch_id"), r["source"], r["status"],
                         json.dumps(r, ensure_ascii=False, allow_nan=False)) for r in new])
                    result["imported"] = len(new)
                    db.execute("INSERT INTO settings VALUES (?,?)", ("import:" + content_hash + ":" + datetime.now(timezone.utc).isoformat(),
                               json.dumps(result, ensure_ascii=False)))
        return result
