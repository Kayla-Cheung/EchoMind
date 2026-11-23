#!/usr/bin/env python3
"""
EchoMind - Read-Only Standalone Interactive Report Generator (LIVE API ONLY)
1. Opens data/pilot.sqlite3 strictly in read-only mode (never deletes or mutates records).
2. Includes all LIVE_LLM_API trials (preserving complete AND failed/incomplete records for honest denominators).
3. Computes every statistic dynamically from actual database records (no hardcoded results or synthetic human norms).
4. Sources memory materials and scenarios from canonical protocol modules (acquisition.py / database design).
5. Escapes embedded JSON and rendered HTML fields to prevent script breakage and XSS.
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import acquisition

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "pilot.sqlite3"
OUTPUT_HTML = ROOT / "EchoMind_Visual_Demo.html"
ROOT_INDEX = ROOT / "index.html"
DOCS_DIR = ROOT / "docs"
DOCS_HTML = DOCS_DIR / "index.html"


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = Path(db_path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"未找到数据库文件：{resolved}")
    uri = resolved.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_live_data_readonly(db_path: Path):
    """Read LIVE_LLM_API records without modifying the database."""
    conn = _connect_readonly(db_path)
    cursor = conn.cursor()

    settings = {}
    try:
        for row in cursor.execute("SELECT key, value FROM settings"):
            try:
                settings[row["key"]] = json.loads(row["value"])
            except Exception:
                settings[row["key"]] = row["value"]
    except Exception as exc:
        print(f"Warning reading settings: {exc}", file=sys.stderr)

    mock_skipped_count = 0
    try:
        row = cursor.execute("SELECT COUNT(*) FROM trials WHERE source != 'LIVE_LLM_API'").fetchone()
        mock_skipped_count = int(row[0]) if row else 0
    except Exception:
        mock_skipped_count = 0

    trials = []
    try:
        query = (
            "SELECT id, created_at, batch_id, source, status, payload FROM trials "
            "WHERE source = 'LIVE_LLM_API' ORDER BY created_at ASC, id ASC"
        )
        for row in cursor.execute(query):
            try:
                payload = json.loads(row["payload"])
                if payload.get("source") == "LIVE_LLM_API":
                    trials.append(payload)
            except Exception:
                continue
    except Exception as exc:
        print(f"Warning reading trials: {exc}", file=sys.stderr)

    snapshots = []
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='acquisition_snapshots'")
        if cursor.fetchone():
            for row in cursor.execute("SELECT id, batch_id, payload FROM acquisition_snapshots ORDER BY rowid ASC"):
                try:
                    snapshots.append(json.loads(row["payload"]))
                except Exception:
                    continue
    except Exception as exc:
        print(f"Warning reading snapshots: {exc}", file=sys.stderr)

    human_counts = {"human_ground_truth": 0, "state_human_datasets": 0}
    for table_name in ("human_ground_truth", "state_human_datasets"):
        try:
            exists = cursor.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
            ).fetchone()
            if exists:
                human_counts[table_name] = int(cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])
        except Exception:
            human_counts[table_name] = 0

    conn.close()
    return settings, trials, snapshots, mock_skipped_count, human_counts


def build_canonical_memory_materials():
    """Build memory materials directly from acquisition.py canonical EVENTS."""
    materials = {
        "none": {
            "name": acquisition.LABELS["none"],
            "type": "基线",
            "text": "（不注入任何前置经历消息，仅发送角色系统提示与当前触发情境）",
            "instruction": "直接呈现触发情境，无额外上下文前缀。",
        }
    }
    instructions = {
        "direct": "单段连贯事实文本（acquisition.memory_messages(event, 'direct') 实际输出）。",
        "transcript": "逐条编号的事件记录（acquisition.memory_messages(event, 'transcript') 实际输出）。",
        "interactive": "两轮固定事件交互提示（acquisition.memory_messages(event, 'interactive') 实际输入，模型逐轮简短回应后冻结上下文）。",
    }
    valence_label = {"neutral": "中性经历", "negative": "负性经历"}
    for method in acquisition.METHODS:
        for valence in ("neutral", "negative"):
            cond = f"{valence}_{method}"
            rendered_msgs = acquisition.memory_messages(acquisition.EVENTS[valence], method)
            if method == "interactive":
                text = "\n\n".join(
                    f"【第 {idx} 轮固定提示】\n{msg['content']}"
                    for idx, msg in enumerate(rendered_msgs, 1)
                )
            else:
                text = "\n\n".join(msg["content"] for msg in rendered_msgs)
            materials[cond] = {
                "name": acquisition.LABELS[cond],
                "type": valence_label[valence],
                "text": text,
                "instruction": instructions[method],
            }
    return materials


def extract_trial_memory_text(record, snapshot_by_id, canonical_materials):
    """Extract the actual injected context from the trial record first, falling back to canonical materials."""
    if record.get("memory_content"):
        mc = record["memory_content"]
        if isinstance(mc, str):
            return mc
        return json.dumps(mc, ensure_ascii=False, indent=2)

    snap_id = record.get("memory_snapshot_id")
    if snap_id and snap_id in snapshot_by_id:
        snap = snapshot_by_id[snap_id]
        snap_msgs = snap.get("messages") or []
        non_system = [m for m in snap_msgs if m.get("role") != "system"]
        if non_system:
            return "\n\n".join(f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in non_system)

    mems = record.get("memories") or (record.get("snapshot") or {}).get("memories")
    if isinstance(mems, list) and mems:
        return "\n".join(
            f"- {m.get('text', str(m))}" if isinstance(m, dict) else f"- {m}"
            for m in mems
        )
    if isinstance(mems, list) and len(mems) == 0:
        return "（无附加前置经历）"

    if record.get("memory_material"):
        return str(record["memory_material"])

    role_msgs = record.get("role_messages")
    if isinstance(role_msgs, list) and len(role_msgs) > 2:
        middle = role_msgs[1:-1]
        if middle:
            return "\n\n".join(f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in middle)
    elif isinstance(role_msgs, list) and len(role_msgs) == 2:
        user_msg = role_msgs[1].get("content", "")
        for marker in ("现在发生了这样一件事：", "今天发生了以下情况：", "现在发生了一个独立的时刻："):
            if marker in user_msg:
                prefix = user_msg.split(marker, 1)[0].strip()
                return prefix if prefix else "（无附加前置经历）"

    cond = record.get("condition") or record.get("condition_id") or "none"
    if cond in canonical_materials:
        return canonical_materials[cond]["text"]
    return "（无附加前置经历）"


def extract_coding_fields(record):
    """Read human review coding if present, otherwise machine coding."""
    coding = (record.get("human_review") or {}).get("coding") or record.get("machine_coding") or {}
    interp = coding.get("interpretation")
    if not interp and isinstance(coding.get("negative_attribution"), dict):
        neg_val = coding["negative_attribution"].get("value")
        interp = "negative" if neg_val == "present" else ("neutral" if neg_val == "absent" else "unclear")
    interp = interp or ("error" if record.get("status") != "complete" else "unclear")

    act = coding.get("action")
    if not act and isinstance(coding.get("actions"), list):
        act = ",".join(str(x) for x in coding["actions"]) if coding["actions"] else "other"
    act = act or ("error" if record.get("status") != "complete" else "other")

    reason = coding.get("coding_reason")
    if not reason:
        if record.get("status") != "complete":
            reason = f"试次未完成（状态：{record.get('status')}；错误：{record.get('error') or '无'}）"
        else:
            reason = "未记录编码理由"

    conf = coding.get("coding_confidence")
    return interp, act, reason, conf


def cond_order(cond: str) -> int:
    if cond in ("none", "baseline", "state_none"):
        return 1
    if cond.startswith("neutral_") or cond in ("positive_self", "positive_social", "neutral_daily", "state_mild"):
        return 2
    if cond.startswith("negative_") or cond in ("negative_self", "negative_other", "negative_social", "negative_nonsocial", "state_moderate"):
        return 3
    return 4


def process_report_data(settings, trials, snapshots, mock_skipped_count=0, human_counts=None):
    design = settings.get("design", {})
    human_counts = human_counts or {"human_ground_truth": 0, "state_human_datasets": 0}
    snapshot_by_id = {s.get("id"): s for s in snapshots if isinstance(s, dict) and s.get("id")}

    condition_labels = {
        **acquisition.LABELS,
        # Demo 1 (memory-ablation-v1)
        "positive_self": "自身经历 · 平稳自传式记忆",
        "negative_self": "自身经历 · 负性排斥自传式记忆",
        "negative_other": "他人经历 · 旁观同伴遭遇排斥",
        "baseline": "不提供经历 (基线对照)",
        # State pilot (memory-ratio-v1)
        "state_none": "平稳经历 (基线对照)",
        "state_mild": "混合经历 (轻度诱导)",
        "state_moderate": "不利经历 (中度诱导)",
        # Legacy
        "positive_social": "正面社交经历注入",
        "negative_social": "负面社交经历注入",
        "negative_nonsocial": "负面非社交经历注入",
        "neutral_daily": "中性日常经历注入",
    }

    canonical_materials = build_canonical_memory_materials()

    # Scenarios from design + scenarios.json + canonical acquisition.SCENARIOS
    scenarios_list = list(design.get("scenarios", []))
    if not scenarios_list and (ROOT / "data" / "scenarios.json").exists():
        try:
            scenarios_list = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))
        except Exception:
            scenarios_list = []

    existing_ids = {s.get("id") or s.get("scenario_id") for s in scenarios_list}
    for asc in acquisition.SCENARIOS:
        if asc["scenario_id"] not in existing_ids:
            scenarios_list.append({
                "id": asc["scenario_id"],
                "kind": asc["scenario_category"],
                "situation": asc["exact_text"],
            })

    scenario_text_map = {}
    for s in scenarios_list:
        sid = s.get("id") or s.get("scenario_id")
        if sid:
            scenario_text_map[sid] = s.get("situation") or s.get("exact_text") or ""

    batches_map = defaultdict(list)
    for r in trials:
        bid = r.get("batch_id") or "unbatched"
        batches_map[bid].append(r)

    batch_list = []
    batch_details = {}
    overall_groups = defaultdict(lambda: {
        "total": 0, "complete": 0, "failed": 0,
        "interp": Counter(), "action": Counter(),
    })

    for bid, rows in batches_map.items():
        statuses = Counter(r.get("status", "unknown") for r in rows)
        complete_count = statuses.get("complete", 0)
        failed_count = len(rows) - complete_count

        protocols = sorted({str(r.get("protocol") or "memory-pilot-v1") for r in rows})
        models = sorted({str(r.get("model") or "unknown") for r in rows})
        sources = sorted({str(r.get("source") or "unknown") for r in rows})
        ts = min((r.get("timestamp") or "" for r in rows), default="")

        batch_list.append({
            "id": bid,
            "timestamp": ts,
            "total": len(rows),
            "complete": complete_count,
            "error": failed_count,
            "protocols": protocols,
            "models": models,
            "sources": sources,
        })

        cond_stats = defaultdict(lambda: {
            "total": 0, "complete": 0, "failed": 0,
            "interp": Counter(), "action": Counter(),
            "samples": [],
        })
        case_comparisons = defaultdict(lambda: defaultdict(list))

        for r in rows:
            cond = r.get("condition") or r.get("condition_id") or "none"
            proto = str(r.get("protocol") or "memory-pilot-v1")
            model_name = str(r.get("model") or "unknown")
            sc_id = r.get("scenario_id") or (r.get("scenario") or {}).get("scenario_id") or "unknown"
            sc_text = (
                (r.get("scenario") or {}).get("exact_text")
                or (r.get("scenario") or {}).get("situation")
                or (r.get("snapshot") or {}).get("scenario", {}).get("situation")
                or scenario_text_map.get(sc_id, "")
            )
            status = r.get("status") or "unknown"
            is_complete = status == "complete"

            c_entry = cond_stats[cond]
            c_entry["total"] += 1
            og_entry = overall_groups[(proto, model_name, cond)]
            og_entry["total"] += 1

            interp, act, reason, conf = extract_coding_fields(r)

            if is_complete:
                c_entry["complete"] += 1
                c_entry["interp"][interp] += 1
                c_entry["action"][act] += 1
                og_entry["complete"] += 1
                og_entry["interp"][interp] += 1
                og_entry["action"][act] += 1
            else:
                c_entry["failed"] += 1
                og_entry["failed"] += 1

            thought = (r.get("channels") or {}).get("thought") or (r.get("agent_parsed") or {}).get("interpretation") or r.get("thought") or ""
            speech = (r.get("channels") or {}).get("speech") or (r.get("agent_parsed") or {}).get("speech") or r.get("speech") or ""
            behavior = (r.get("channels") or {}).get("behavior") or (r.get("agent_parsed") or {}).get("action") or r.get("behavior") or ""
            narrative = r.get("narrative") or ""
            if not thought and narrative:
                thought = narrative

            memory_text = extract_trial_memory_text(r, snapshot_by_id, canonical_materials)

            sample_item = {
                "id": str(r.get("id", ""))[:8],
                "status": status,
                "error": r.get("error") or "",
                "protocol": proto,
                "scenario_id": sc_id,
                "scenario_text": sc_text,
                "condition": cond,
                "condition_label": condition_labels.get(cond, cond),
                "memory_text": memory_text,
                "thought": thought,
                "speech": speech,
                "behavior": behavior,
                "interpretation": interp,
                "action": act,
                "reason": reason,
                "confidence": conf,
                "model": model_name,
                "evaluator_model": r.get("evaluator_model") or "独立编码员大模型",
                "repeat": r.get("repeat", 1),
            }

            c_entry["samples"].append(sample_item)
            if is_complete:
                case_comparisons[sc_id][cond].append(sample_item)

        summary_table = []
        for cond, val in cond_stats.items():
            complete_n = val["complete"]
            neg_count = val["interp"].get("negative", 0)
            avoid_count = val["action"].get("avoid", 0)
            summary_table.append({
                "condition": cond,
                "label": condition_labels.get(cond, cond),
                "total": val["total"],
                "complete": complete_n,
                "failed": val["failed"],
                "neg_count": neg_count,
                "neg_rate": round(neg_count / complete_n * 100, 1) if complete_n > 0 else 0.0,
                "avoid_count": avoid_count,
                "avoid_rate": round(avoid_count / complete_n * 100, 1) if complete_n > 0 else 0.0,
                "interp_dist": dict(val["interp"]),
                "action_dist": dict(val["action"]),
            })
        summary_table.sort(key=lambda x: (cond_order(x["condition"]), x["condition"]))

        batch_details[bid] = {
            "summary_table": summary_table,
            "all_samples": [s for val in cond_stats.values() for s in val["samples"]],
            "case_comparisons": {sc: dict(cmap) for sc, cmap in case_comparisons.items()},
        }

    batch_list.sort(key=lambda x: x["timestamp"], reverse=True)

    # Full-database honest aggregate across protocol x model x condition
    overall_matrix = []
    for (proto, model_name, cond), val in sorted(
        overall_groups.items(), key=lambda kv: (kv[0][0], kv[0][1], cond_order(kv[0][2]), kv[0][2])
    ):
        complete_n = val["complete"]
        neg_count = val["interp"].get("negative", 0)
        avoid_count = val["action"].get("avoid", 0)
        overall_matrix.append({
            "protocol": proto,
            "model": model_name,
            "condition": cond,
            "condition_label": condition_labels.get(cond, cond),
            "total": val["total"],
            "complete": complete_n,
            "failed": val["failed"],
            "neg_count": neg_count,
            "neg_rate": round(neg_count / complete_n * 100, 1) if complete_n > 0 else 0.0,
            "avoid_count": avoid_count,
            "avoid_rate": round(avoid_count / complete_n * 100, 1) if complete_n > 0 else 0.0,
            "interp_dist": dict(val["interp"]),
            "action_dist": dict(val["action"]),
        })

    total_complete = sum(1 for r in trials if r.get("status") == "complete")
    total_failed = len(trials) - total_complete
    models_used = sorted({str(r.get("model") or "unknown") for r in trials})

    identity = design.get("identity", {"name": "林知", "description": "20岁大学生"})
    acq_system = acquisition.base_message(identity)["content"]

    prompt_inspector = {
        "identity": identity,
        "system_prompt": design.get("system_prompt", acq_system),
        "acquisition_system_prompt": acq_system,
        "coding_rules": design.get(
            "coding_rules",
            "只依据原始文本可观察内容。\n"
            "解释 interpretation：positive（正面理解），neutral（中性或多种可能并存），negative（明确排斥、贬低或负面归因），unclear（无法判断）。\n"
            "行动 action：approach（主动联系、继续参与或主动处理问题），wait（明确等待或观察），avoid（明确减少接触、退出参与或放弃处理），other（其他或无法判断）。\n"
            "coding_confidence 用 0 到 1 的数字；coding_reason 是简短可观察的原文依据。",
        ),
        "memory_materials": canonical_materials,
        "scenarios": scenarios_list,
        "evaluator_schema": {
            "interpretation": "positive | neutral | negative | unclear",
            "action": "approach | wait | avoid | other",
            "coding_confidence": "float (0.0 - 1.0)",
            "coding_reason": "简短引用原文作为打标判定的依据",
        },
    }

    return {
        "batches": batch_list,
        "batch_details": batch_details,
        "overall_matrix": overall_matrix,
        "condition_labels": condition_labels,
        "prompt_inspector": prompt_inspector,
        "limitations": list(acquisition.LIMITATIONS),
        "human_data_status": {
            "human_ground_truth_rows": human_counts["human_ground_truth"],
            "state_human_datasets_rows": human_counts["state_human_datasets"],
            "verified": (human_counts["human_ground_truth"] + human_counts["state_human_datasets"]) > 0,
            "notice": (
                "当前数据库尚未导入同范式逐题真实人类对照数据（human_ground_truth=0, state_human_datasets=0），"
                "因此外部人类拟合度标为【未检验】。本报告严禁使用硬编码的跨论文均值或合成人类常模替代实测对照。"
            ),
        },
        "summary_meta": {
            "total_live_records": len(trials),
            "complete_live_records": total_complete,
            "failed_live_records": total_failed,
            "mock_records_excluded_readonly": mock_skipped_count,
            "models": models_used,
            "snapshots_count": len(snapshots),
        },
        "total_records": len(trials),
        "exported_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
    }


def safe_json_for_script(data) -> str:
    """Serialize JSON safely for inline <script> embedding without </script> or HTML breakout."""
    raw = json.dumps(data, ensure_ascii=False)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def generate_html(data):
    json_payload = safe_json_for_script(data)
    meta = data["summary_meta"]
    models_text = "、".join(meta["models"]) if meta["models"] else "（暂无真实模型记录）"

    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EchoMind · 实验台成果全景看板与提示词透视 (只读真实 API 审计报告)</title>
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: #131b2a;
      --card-hover: #172235;
      --card-border: #233148;
      --text-main: #e2e8f0;
      --text-muted: #8fa1b8;
      --text-dim: #5c6e86;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.2);
      --negative: #f43f5e;
      --negative-glow: rgba(244, 63, 94, 0.18);
      --avoid: #fbbf24;
      --avoid-glow: rgba(251, 191, 36, 0.18);
      --neutral: #38bdf8;
      --approach: #34d399;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font-sans);
      background: var(--bg);
      color: var(--text-main);
      line-height: 1.6;
      padding-bottom: 80px;
    }}
    header {{
      background: rgba(9, 13, 22, 0.88);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--card-border);
      padding: 16px 36px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .brand h1 {{
      font-size: 1.35rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #fff, #94a3b8);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .live-badge {{
      background: rgba(52, 211, 153, 0.15);
      color: #34d399;
      border: 1px solid rgba(52, 211, 153, 0.4);
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .live-badge::before {{
      content: "";
      display: inline-block;
      width: 7px;
      height: 7px;
      background: #34d399;
      border-radius: 50%;
      box-shadow: 0 0 8px #34d399;
    }}
    .header-meta {{
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
    .container {{
      max-width: 1400px;
      margin: 28px auto;
      padding: 0 28px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.08) 0%, rgba(19, 27, 42, 0.95) 100%);
      border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 12px;
      padding: 26px 30px;
      margin-bottom: 24px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
    }}
    .hero h2 {{
      font-size: 1.55rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .hero p {{
      color: var(--text-muted);
      font-size: 0.95rem;
      line-height: 1.7;
    }}
    .live-alert {{
      margin-top: 14px;
      background: rgba(52, 211, 153, 0.08);
      border: 1px solid rgba(52, 211, 153, 0.25);
      border-radius: 6px;
      padding: 10px 16px;
      font-size: 0.88rem;
      color: #a7f3d0;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .warn-box {{
      margin-top: 12px;
      background: rgba(251, 191, 36, 0.08);
      border: 1px solid rgba(251, 191, 36, 0.35);
      border-radius: 6px;
      padding: 12px 16px;
      font-size: 0.88rem;
      color: #fde68a;
      line-height: 1.7;
    }}
    .controls-strip {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 16px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 16px 24px;
      margin-bottom: 24px;
    }}
    .batch-control {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .batch-control label {{
      font-weight: 600;
      font-size: 0.92rem;
      color: #fff;
    }}
    select, input {{
      background: #080d16;
      border: 1px solid var(--card-border);
      color: var(--text-main);
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 0.9rem;
      outline: none;
      transition: all 0.2s;
    }}
    select:focus, input:focus {{
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-glow);
    }}
    .tabs-nav {{
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 24px;
      overflow-x: auto;
    }}
    .tab-btn {{
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 0.98rem;
      font-weight: 600;
      padding: 12px 20px;
      cursor: pointer;
      border-bottom: 3px solid transparent;
      transition: all 0.2s ease;
      white-space: nowrap;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .tab-btn:hover {{
      color: #fff;
      background: rgba(255, 255, 255, 0.02);
    }}
    .tab-btn.active {{
      color: var(--accent);
      border-bottom-color: var(--accent);
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }}
    .card h3 {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .card-subtitle {{
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-bottom: 20px;
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric-card {{
      background: #080d16;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 18px;
      text-align: center;
    }}
    .metric-card .num {{
      font-size: 2.1rem;
      font-weight: 800;
      color: #fff;
      line-height: 1.1;
      margin-bottom: 6px;
      font-family: var(--font-mono);
    }}
    .metric-card .label {{
      font-size: 0.8rem;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .comparison-filter-bar {{
      background: #080d16;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px 18px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .comparison-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 20px;
    }}
    .case-card {{
      background: #0b111e;
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      position: relative;
      transition: transform 0.2s, border-color 0.2s;
    }}
    .case-card:hover {{
      border-color: #3b5072;
      transform: translateY(-2px);
    }}
    .case-card.is-negative {{ border-top: 4px solid var(--negative); }}
    .case-card.is-neutral {{ border-top: 4px solid var(--neutral); }}
    .case-card.is-baseline {{ border-top: 4px solid #64748b; }}
    .case-card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
      gap: 8px;
    }}
    .case-title {{
      font-size: 1.02rem;
      font-weight: 700;
      color: #fff;
    }}
    .case-injected-box {{
      background: rgba(255, 255, 255, 0.03);
      border-left: 3px solid #38bdf8;
      border-radius: 4px;
      padding: 10px 14px;
      font-size: 0.85rem;
      color: #cbd5e1;
      margin-bottom: 14px;
      white-space: pre-wrap;
    }}
    .case-section-title {{
      font-size: 0.74rem;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-dim);
      margin-bottom: 6px;
      letter-spacing: 0.5px;
    }}
    .sample-nav-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: rgba(0,0,0,0.3);
      border-radius: 4px;
      padding: 4px 10px;
      margin-bottom: 12px;
      font-size: 0.8rem;
      color: var(--text-muted);
    }}
    .sample-nav-btn {{
      background: none;
      border: 1px solid var(--card-border);
      color: var(--text-main);
      padding: 2px 8px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.75rem;
    }}
    .sample-nav-btn:hover {{
      background: rgba(255,255,255,0.1);
      color: #fff;
    }}
    .bubble {{
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 12px;
      font-size: 0.9rem;
      line-height: 1.6;
      white-space: pre-wrap;
    }}
    .bubble-thought {{
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.25);
      color: #e0f2fe;
    }}
    .bubble-speech {{
      background: rgba(52, 211, 153, 0.08);
      border: 1px solid rgba(52, 211, 153, 0.25);
      color: #d1fae5;
    }}
    .bubble-behavior {{
      background: rgba(251, 191, 36, 0.08);
      border: 1px solid rgba(251, 191, 36, 0.25);
      color: #fef3c7;
    }}
    .bubble-label {{
      font-size: 0.75rem;
      font-weight: 700;
      display: block;
      margin-bottom: 4px;
      text-transform: uppercase;
    }}
    .label-thought {{ color: var(--accent); }}
    .label-speech {{ color: var(--approach); }}
    .label-behavior {{ color: var(--avoid); }}
    .judge-panel {{
      background: #060910;
      border: 1px solid #1f2937;
      border-radius: 6px;
      padding: 12px 14px;
      margin-top: auto;
      font-size: 0.84rem;
    }}
    .judge-tags {{
      display: flex;
      gap: 8px;
      margin-bottom: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .judge-reason {{
      color: var(--text-muted);
      font-size: 0.82rem;
    }}
    .bar-row {{
      display: flex;
      align-items: center;
      margin-bottom: 14px;
      font-size: 0.92rem;
    }}
    .bar-label {{
      width: 260px;
      flex-shrink: 0;
      color: var(--text-main);
      font-weight: 500;
    }}
    .bar-track {{
      flex: 1;
      height: 32px;
      background: #080d16;
      border-radius: 6px;
      overflow: hidden;
      display: flex;
      border: 1px solid var(--card-border);
      margin: 0 16px;
      position: relative;
    }}
    .bar-fill {{
      height: 100%;
      transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      align-items: center;
      padding-left: 10px;
      font-size: 0.82rem;
      font-weight: 700;
      color: #fff;
      font-family: var(--font-mono);
      white-space: nowrap;
    }}
    .bar-fill.negative {{ background: linear-gradient(90deg, #e11d48, #f43f5e); }}
    .bar-fill.avoidance {{ background: linear-gradient(90deg, #d97706, #fbbf24); }}
    .bar-value {{
      width: 110px;
      text-align: right;
      font-family: var(--font-mono);
      font-weight: 600;
      color: #fff;
    }}
    .pipeline-step {{
      background: #090e18;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      margin-bottom: 20px;
      overflow: hidden;
    }}
    .pipeline-step-header {{
      background: #0e1626;
      padding: 12px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--card-border);
    }}
    .pipeline-step-header h4 {{
      font-size: 1rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pipeline-code {{
      padding: 18px 20px;
      font-family: var(--font-mono);
      font-size: 0.88rem;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
      color: #93c5fd;
    }}
    .pill-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 18px;
    }}
    .pill-btn {{
      background: #090e18;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 6px 14px;
      border-radius: 999px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
    }}
    .pill-btn:hover {{
      color: #fff;
      border-color: #3b5072;
    }}
    .pill-btn.active {{
      background: var(--accent);
      color: #090d16;
      border-color: var(--accent);
    }}
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }}
    .tag-negative {{ background: var(--negative-glow); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.4); }}
    .tag-avoid {{ background: var(--avoid-glow); color: #fde047; border: 1px solid rgba(251, 191, 36, 0.4); }}
    .tag-neutral {{ background: rgba(56, 189, 248, 0.15); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.4); }}
    .tag-positive {{ background: rgba(52, 211, 153, 0.15); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.4); }}
    .tag-approach {{ background: rgba(52, 211, 153, 0.15); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.4); }}
    .tag-wait {{ background: rgba(251, 191, 36, 0.15); color: #fde047; border: 1px solid rgba(251, 191, 36, 0.4); }}
    .tag-unclear, .tag-other, .tag-error {{ background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.3); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      text-align: left;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--card-border);
      vertical-align: top;
    }}
    th {{
      background: #080d16;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.78rem;
      letter-spacing: 0.5px;
    }}
    tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
    .trials-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
      gap: 18px;
      margin-top: 18px;
    }}
    .trial-card {{
      background: #0a0f1b;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 20px;
      display: flex;
      flex-direction: column;
    }}
    .trial-card-head {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 12px;
      gap: 8px;
    }}
    .limitations-list {{
      padding-left: 20px;
      color: var(--text-muted);
      line-height: 1.85;
      font-size: 0.92rem;
    }}
  </style>
</head>
<body>

<header>
  <div class="brand">
    <h1>EchoMind</h1>
    <span class="live-badge">只读真实 API 审计报告</span>
  </div>
  <div class="header-meta">
    <span>共 {meta["total_live_records"]} 条真实 API 试次（完成 {meta["complete_live_records"]} / 未完成 {meta["failed_live_records"]}）· 导出时间：{data["exported_at"]}</span>
  </div>
</header>

<div class="container">
  <div class="hero">
    <h2>🔬 EchoMind · LLM 上下文记忆与模糊情境决策实测看板</h2>
    <p>
      本报告从本地 SQLite 数据库以<strong>纯只读模式</strong>导出，仅纳入 <code>source = LIVE_LLM_API</code> 的真实模型调用记录（保留完整分母与失败数，不修改原数据库），所有统计均由实测记录动态计算，包含真实零效应与未检出差异的批次。
    </p>
    <div class="live-alert">
      <span>🟢 <strong>实测来源：</strong>覆盖模型 <strong>{models_text}</strong>；共 <strong>{meta["total_live_records"]}</strong> 条真实 API 试次（已只读排除 MOCK 记录 {meta["mock_records_excluded_readonly"]} 条，数据库原记录未被删除）。</span>
    </div>
  </div>

  <div class="controls-strip">
    <div class="batch-control">
      <label for="batchSelect">选择真实实验批次：</label>
      <select id="batchSelect" style="min-width: 380px;"></select>
    </div>
    <div id="batchMeta" style="font-size: 0.88rem; color: var(--text-muted);"></div>
  </div>

  <div class="tabs-nav">
    <button class="tab-btn active" onclick="switchTab('tab-comparison', this)">💡 同题对照案例 (Side-by-Side)</button>
    <button class="tab-btn" onclick="switchTab('tab-prompts', this)">🔍 提示词装配全景 (Prompt Pipeline)</button>
    <button class="tab-btn" onclick="switchTab('tab-charts', this)">📊 实测统计与全库汇总 (Distributions)</button>
    <button class="tab-btn" onclick="switchTab('tab-records', this)">📋 全量试次明细 (Explorer)</button>
    <button class="tab-btn" onclick="switchTab('tab-protocol', this)">📑 学术边界与局限声明</button>
  </div>

  <!-- TAB 1 -->
  <div id="tab-comparison" class="tab-pane">
    <div class="card">
      <div class="card-header">
        <h3>💡 同题对照：同一模糊情境下的真实模型输出对比</h3>
      </div>
      <p class="card-subtitle">
        展示当前所选批次中、同一情境下各实验条件实际注入的前置上下文与模型原始输出（含自由文本与三通道结构化结果）：
      </p>

      <div class="comparison-filter-bar">
        <label for="scenarioSelector" style="font-weight: 700; color:#fff;">选择测试情境：</label>
        <select id="scenarioSelector" style="flex: 1; max-width: 700px;"></select>
      </div>

      <div id="scenarioDescriptionBox" style="background:#060a12; border: 1px solid var(--card-border); border-radius: 8px; padding: 16px 20px; margin-bottom: 24px;">
        <span style="font-size: 0.75rem; font-weight:700; color:var(--accent); text-transform:uppercase;">情境输入 (Trigger Situation)：</span>
        <p id="scenarioCurrentText" style="font-size: 1rem; color:#fff; margin-top: 6px; font-weight: 500;"></p>
      </div>

      <div class="comparison-grid" id="comparisonCardsGrid"></div>
    </div>
  </div>

  <!-- TAB 2 -->
  <div id="tab-prompts" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>🔍 Prompt Pipeline · 代码库权威提示词与材料原文</h3>
      <p class="card-subtitle">
        直接从 <code>acquisition.py</code> 与数据库 <code>design</code> 配置生成，与实际发送给模型的提示结构严格保持一致。
      </p>

      <div class="pipeline-step">
        <div class="pipeline-step-header">
          <h4>1. 基础人设指令 (System Role Prompt)</h4>
          <span class="tag tag-neutral">数据库当前配置</span>
        </div>
        <div class="pipeline-code" id="systemPromptDisplay"></div>
      </div>

      <div class="pipeline-step">
        <div class="pipeline-step-header">
          <h4>2. Memory Acquisition v0.2 权威事件材料 (来自 acquisition.py EVENTS)</h4>
          <span class="tag tag-neutral">7 种对照条件</span>
        </div>
        <div style="padding: 16px 20px 0 20px;">
          <div class="pill-list" id="memoryPillList"></div>
        </div>
        <div class="pipeline-code" id="memoryMaterialDisplay"></div>
      </div>

      <div class="pipeline-step">
        <div class="pipeline-step-header">
          <h4>3. 独立评判编码规范 (Coder / Evaluator Rules)</h4>
          <span class="tag tag-neutral">独立上下文盲评</span>
        </div>
        <div class="pipeline-code" id="evaluatorPromptDisplay"></div>
      </div>

      <div class="pipeline-step">
        <div class="pipeline-step-header">
          <h4>4. 模糊情境测试库 (Trigger Scenarios Library)</h4>
          <span class="tag tag-neutral">标准化测试集</span>
        </div>
        <div style="padding: 16px 20px;" id="scenariosLibraryDisplay"></div>
      </div>
    </div>
  </div>

  <!-- TAB 3 -->
  <div id="tab-charts" class="tab-pane" style="display:none;">
    <div class="metrics-grid" id="metricsGrid"></div>

    <div class="card">
      <h3>📈 当前批次：各条件负面解释占比 (Negative Attribution %)</h3>
      <p class="card-subtitle">
        分母为当前批次各条件的完整编码样本数（包含 unclear）；未完成/失败试次在下方汇总表中单独列示。
      </p>
      <div id="negativeChartContainer"></div>
    </div>

    <div class="card">
      <h3>📉 当前批次：各条件回避行动占比 (Avoidance Action %)</h3>
      <p class="card-subtitle">
        分母为当前批次各条件的完整编码样本数（包含 other）；行动为模型生成的行动意向文本，并非真实人类行为。
      </p>
      <div id="avoidChartContainer"></div>
    </div>

    <div class="card">
      <h3>📋 当前批次结构化量化统计表</h3>
      <div style="overflow-x: auto;">
        <table id="summaryTable">
          <thead>
            <tr>
              <th>实验策略条件</th>
              <th>完成 / 总计（失败）</th>
              <th>负面归因数 / 占比</th>
              <th>回避行动数 / 占比</th>
              <th>解释标签全量分布</th>
              <th>行动意向全量分布</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h3>📊 全库实测总表（跨协议 × 跨模型 × 跨条件）</h3>
      <p class="card-subtitle">
        汇总当前 SQLite 数据库中全部真实 API 试次，不同协议独立分行、不跨协议混池，完整呈现正结果与零效应反例：
      </p>
      <div style="overflow-x: auto;">
        <table id="overallMatrixTable">
          <thead>
            <tr>
              <th>协议</th>
              <th>角色模型</th>
              <th>实验条件</th>
              <th>完成 / 总计（失败）</th>
              <th>负面归因</th>
              <th>回避行动</th>
              <th>解释分布</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <div class="card" style="border: 1px solid rgba(251, 191, 36, 0.35);">
      <h3>👤 人类参照数据状态与外部效度核查</h3>
      <div id="humanStatusBox" class="warn-box"></div>
    </div>
  </div>

  <!-- TAB 4 -->
  <div id="tab-records" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>📋 全量真实试次与打标明细</h3>
      <p class="card-subtitle">
        按关键词、实验条件、解释标签和行动意向筛选当前批次的全部真实 API 试次：
      </p>

      <div class="controls-strip" style="margin-bottom: 20px; padding: 12px 18px;">
        <input type="text" id="searchInput" placeholder="搜索关键词（如：图表、退出、理由...）" style="flex:1; min-width: 250px;">
        <select id="filterCondition"><option value="">全部实验条件</option></select>
        <select id="filterInterp">
          <option value="">全部解释倾向</option>
          <option value="negative">负面 (negative)</option>
          <option value="neutral">中性 (neutral)</option>
          <option value="positive">正面 (positive)</option>
          <option value="unclear">未知 (unclear)</option>
          <option value="error">未完成/错误 (error)</option>
        </select>
        <select id="filterAction">
          <option value="">全部行动意向</option>
          <option value="avoid">回避 (avoid)</option>
          <option value="approach">靠近 (approach)</option>
          <option value="wait">等待 (wait)</option>
          <option value="other">其他 (other)</option>
          <option value="error">未完成/错误 (error)</option>
        </select>
      </div>

      <div class="trials-grid" id="trialsCardsContainer"></div>
    </div>
  </div>

  <!-- TAB 5 -->
  <div id="tab-protocol" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>📑 实验设计与学术边界声明</h3>
      <div style="line-height: 1.85; font-size: 0.94rem; color: var(--text-main); margin-bottom: 18px;">
        <p><strong>1. 研究范围定位：</strong>本工作台检验受控上下文/记忆注入对 LLM 公开文本解释与行动意向分布的影响。<strong>不声称模型拥有焦虑、创伤等主观心理状态，也不以重复采样替代独立人类被试</strong>。</p>
        <br>
        <p><strong>2. 只读审计与完整分母：</strong>本报告由数据库只读生成，不修改或删除任何历史试次；仅展示 <code>LIVE_LLM_API</code> 记录，并保留完整/失败分母与零效应结果。</p>
        <br>
        <p><strong>3. 协议明确局限（源自 <code>acquisition.py</code>）：</strong></p>
      </div>
      <ul class="limitations-list" id="limitationsList"></ul>
    </div>
  </div>
</div>

<script>
const DATA = {json_payload};

let currentBatchId = DATA.batches[0]?.id || "";
let selectedMemoryKey = "negative_direct";
let sampleIndices = {{}};

function escapeHtml(str) {{
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}}

function safeTagClass(prefix, value) {{
  const allowed = new Set(["negative", "neutral", "positive", "unclear", "avoid", "approach", "wait", "other", "error"]);
  const v = allowed.has(value) ? value : "unclear";
  return prefix + "-" + v;
}}

function init() {{
  const select = document.getElementById("batchSelect");
  if (!DATA.batches.length) {{
    select.innerHTML = '<option value="">(暂无可用的真实 API 批次)</option>';
    renderOverallAndHumanStatus();
    renderPromptsView();
    renderLimitations();
    return;
  }}

  select.innerHTML = DATA.batches.map(b => {{
    const modelStr = (b.models || []).join(", ") || "LLM";
    const protoStr = (b.protocols || []).join(", ");
    const label = `${{(b.timestamp || "").slice(0, 10)}} · ${{(b.id || "").slice(0, 8)}} (${{b.complete}}/${{b.total}}条) [${{protoStr}} | ${{modelStr}}]`;
    return `<option value="${{escapeHtml(b.id)}}">${{escapeHtml(label)}}</option>`;
  }}).join("");

  select.onchange = (e) => {{
    currentBatchId = e.target.value;
    sampleIndices = {{}};
    renderAllViews();
  }};

  document.getElementById("scenarioSelector").onchange = () => {{
    sampleIndices = {{}};
    renderCaseComparison();
  }};

  renderAllViews();
  renderOverallAndHumanStatus();
  renderPromptsView();
  renderLimitations();
}}

function switchTab(tabId, btnEl) {{
  document.querySelectorAll(".tab-pane").forEach(el => el.style.display = "none");
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  document.getElementById(tabId).style.display = "block";
  if (btnEl) btnEl.classList.add("active");
}}

function updateScenarioDropdown() {{
  const scSelect = document.getElementById("scenarioSelector");
  const detail = DATA.batch_details[currentBatchId];
  if (!detail || !detail.case_comparisons) {{
    scSelect.innerHTML = '<option value="">(当前批次无情境数据)</option>';
    return;
  }}

  const availableScIds = Object.keys(detail.case_comparisons);
  if (!availableScIds.length) {{
    scSelect.innerHTML = '<option value="">(当前批次无情境数据)</option>';
    return;
  }}

  const prev = scSelect.value;
  scSelect.innerHTML = availableScIds.map(scId => {{
    let text = "";
    const condKeys = Object.keys(detail.case_comparisons[scId]);
    if (condKeys.length && detail.case_comparisons[scId][condKeys[0]]?.length) {{
      text = detail.case_comparisons[scId][condKeys[0]][0].scenario_text || "";
    }}
    if (!text) {{
      const matchObj = DATA.prompt_inspector.scenarios.find(s => (s.id || s.scenario_id) === scId);
      text = matchObj?.situation || matchObj?.exact_text || scId;
    }}
    return `<option value="${{escapeHtml(scId)}}">${{escapeHtml(scId)}} · ${{escapeHtml(text.slice(0, 36))}}...</option>`;
  }}).join("");

  scSelect.value = availableScIds.includes(prev) ? prev : availableScIds[0];
}}

function renderAllViews() {{
  renderBatchMeta();
  updateScenarioDropdown();
  renderCaseComparison();
  renderCharts();
  renderExplorer();
}}

function renderBatchMeta() {{
  const b = DATA.batches.find(x => x.id === currentBatchId);
  if (!b) return;
  document.getElementById("batchMeta").innerHTML =
    `🟢 <strong>批次：</strong><code>${{escapeHtml(b.id)}}</code> | <strong>协议：</strong>${{escapeHtml((b.protocols || []).join(", "))}} | <strong>模型：</strong>${{escapeHtml((b.models || []).join(", "))}} | <strong>完成/总计：</strong>${{b.complete}} / ${{b.total}}（失败 ${{b.error}}）`;
}}

function renderCaseComparison() {{
  const detail = DATA.batch_details[currentBatchId];
  const container = document.getElementById("comparisonCardsGrid");

  if (!detail || !detail.case_comparisons) {{
    container.innerHTML = "<p style='color:var(--text-muted);'>当前批次暂无可用的同题对照数据。</p>";
    return;
  }}

  const scId = document.getElementById("scenarioSelector").value;
  const condMap = detail.case_comparisons[scId];
  if (!condMap || !Object.keys(condMap).length) {{
    container.innerHTML = "<p style='color:var(--text-muted); padding:20px 0;'>该情境在当前批次中无可用对照数据。</p>";
    return;
  }}

  const firstCond = Object.keys(condMap)[0];
  const firstTrial = condMap[firstCond]?.[0];
  let curScenarioText = firstTrial?.scenario_text || "";
  if (!curScenarioText) {{
    const matchObj = DATA.prompt_inspector.scenarios.find(s => (s.id || s.scenario_id) === scId);
    curScenarioText = matchObj?.situation || matchObj?.exact_text || "情境文本";
  }}
  document.getElementById("scenarioCurrentText").textContent = curScenarioText;

  const availableConds = Object.keys(condMap);
  const orderRank = (c) => {{
    if (c === "none" || c === "baseline" || c === "state_none") return 1;
    if (c.startsWith("neutral_") || c === "positive_self" || c === "positive_social" || c === "neutral_daily" || c === "state_mild") return 2;
    if (c.startsWith("negative_") || c === "negative_self" || c === "negative_other" || c === "negative_social" || c === "negative_nonsocial" || c === "state_moderate") return 3;
    return 4;
  }};
  availableConds.sort((a, b) => orderRank(a) - orderRank(b) || a.localeCompare(b));

  container.innerHTML = availableConds.map(condKey => {{
    const trials = condMap[condKey] || [];
    if (!trials.length) return "";

    const curIndex = sampleIndices[condKey] || 0;
    const safeIndex = ((curIndex % trials.length) + trials.length) % trials.length;
    const t = trials[safeIndex];

    const isNeg = condKey.includes("negative") || t.interpretation === "negative";
    const isNeu = condKey.includes("neutral") || condKey.includes("positive") || t.interpretation === "neutral";
    const cardClass = isNeg ? "is-negative" : isNeu ? "is-neutral" : "is-baseline";

    return `
      <div class="case-card ${{cardClass}}">
        <div class="case-card-header">
          <span class="case-title">${{escapeHtml(t.condition_label || condKey)}}</span>
          <span class="tag ${{safeTagClass('tag', t.interpretation)}}">${{escapeHtml(t.interpretation)}}</span>
        </div>

        ${{trials.length > 1 ? `
          <div class="sample-nav-bar">
            <span>样本 ${{safeIndex + 1}} / ${{trials.length}}（重复试次）</span>
            <div>
              <button class="sample-nav-btn" data-cond="${{escapeHtml(condKey)}}" data-delta="-1" onclick="stepSampleBtn(this)">◀ 上一条</button>
              <button class="sample-nav-btn" data-cond="${{escapeHtml(condKey)}}" data-delta="1" onclick="stepSampleBtn(this)">下一条 ▶</button>
            </div>
          </div>
        ` : ""}}

        <div class="case-section-title">实际注入的前置上下文记忆：</div>
        <div class="case-injected-box">${{escapeHtml(t.memory_text || "（无附加前置经历）")}}</div>

        <div class="case-section-title">模型第一人称回答：</div>
        ${{t.thought ? `
          <div class="bubble bubble-thought">
            <div class="bubble-label label-thought">🧠 内心想法 / 公开解释</div>
            ${{escapeHtml(t.thought)}}
          </div>` : ""}}

        ${{t.speech ? `
          <div class="bubble bubble-speech">
            <div class="bubble-label label-speech">💬 公开说话 (Speech)</div>
            ${{escapeHtml(t.speech)}}
          </div>` : ""}}

        ${{t.behavior ? `
          <div class="bubble bubble-behavior">
            <div class="bubble-label label-behavior">🚶 行动意向 (Action)</div>
            ${{escapeHtml(t.behavior)}}
          </div>` : ""}}

        <div class="judge-panel">
          <div class="judge-tags">
            <span class="tag ${{safeTagClass('tag', t.interpretation)}}">归因: ${{escapeHtml(t.interpretation)}}</span>
            <span class="tag ${{safeTagClass('tag', t.action)}}">行动: ${{escapeHtml(t.action)}}</span>
            <span style="font-size:0.75rem; color:var(--text-dim); margin-left:auto;">${{escapeHtml(t.model)}}</span>
          </div>
          <div class="judge-reason"><strong>打标引证：</strong>${{escapeHtml(t.reason)}}</div>
        </div>
      </div>
    `;
  }}).join("");
}}

function stepSampleBtn(btn) {{
  const condKey = btn.getAttribute("data-cond");
  const delta = Number(btn.getAttribute("data-delta")) || 0;
  sampleIndices[condKey] = (sampleIndices[condKey] || 0) + delta;
  renderCaseComparison();
}}

function renderPromptsView() {{
  const p = DATA.prompt_inspector;
  document.getElementById("systemPromptDisplay").textContent =
    "【通用工作台人设提示】：\\n" + p.system_prompt +
    "\\n\\n【Memory Acquisition v0.2 系统提示（acquisition.base_message）】：\\n" + p.acquisition_system_prompt;

  const pillList = document.getElementById("memoryPillList");
  const keys = Object.keys(p.memory_materials);
  if (!keys.includes(selectedMemoryKey) && keys.length) selectedMemoryKey = keys[0];
  pillList.innerHTML = keys.map(k => `
    <button class="pill-btn ${{k === selectedMemoryKey ? "active" : ""}}" data-key="${{escapeHtml(k)}}" onclick="selectMemoryPill(this)">
      ${{escapeHtml(p.memory_materials[k].name)}}
    </button>
  `).join("");

  updateMemoryDisplay();

  document.getElementById("evaluatorPromptDisplay").textContent =
    "【裁判系统指令】：你是独立文本编码员。仅依据提供的情境和原始回答，不猜测人物经历、实验条件或研究者预期。不得从缺失的信息推断负面解释或回避行动。\\n\\n" +
    p.coding_rules + "\\n\\n【严格输出 JSON Schema 规范】：\\n" + JSON.stringify(p.evaluator_schema, null, 2);

  const scList = p.scenarios || [];
  document.getElementById("scenariosLibraryDisplay").innerHTML = scList.map(s => `
    <div style="background:#060a12; border:1px solid var(--card-border); border-radius:6px; padding:12px 16px; margin-bottom:10px;">
      <div style="font-weight:700; color:#fff; font-size:0.92rem; margin-bottom:4px;">
        <span class="tag tag-neutral" style="margin-right:8px;">${{escapeHtml(s.id || s.scenario_id)}}</span>
        ${{s.kind ? `[${{escapeHtml(s.kind)}}]` : ""}}
      </div>
      <p style="font-size:0.88rem; color:#cbd5e1;">${{escapeHtml(s.situation || s.exact_text)}}</p>
    </div>
  `).join("");
}}

function selectMemoryPill(btnEl) {{
  selectedMemoryKey = btnEl.getAttribute("data-key");
  document.querySelectorAll(".pill-btn").forEach(btn => btn.classList.remove("active"));
  btnEl.classList.add("active");
  updateMemoryDisplay();
}}

function updateMemoryDisplay() {{
  const item = DATA.prompt_inspector.memory_materials[selectedMemoryKey];
  if (!item) return;
  document.getElementById("memoryMaterialDisplay").textContent =
    `【策略名称】：${{item.name}}\\n【装配说明】：${{item.instruction}}\\n\\n【权威注入文本正文】：\\n${{item.text}}`;
}}

function renderCharts() {{
  const detail = DATA.batch_details[currentBatchId] || {{ summary_table: [] }};
  const table = detail.summary_table;

  const totalAll = table.reduce((a, b) => a + b.total, 0);
  const totalComplete = table.reduce((a, b) => a + b.complete, 0);
  const totalFailed = table.reduce((a, b) => a + b.failed, 0);
  const totalNeg = table.reduce((a, b) => a + b.neg_count, 0);
  const totalAvoid = table.reduce((a, b) => a + b.avoid_count, 0);
  const avgNeg = totalComplete ? (totalNeg / totalComplete * 100).toFixed(1) : "0.0";
  const avgAvoid = totalComplete ? (totalAvoid / totalComplete * 100).toFixed(1) : "0.0";

  document.getElementById("metricsGrid").innerHTML = `
    <div class="metric-card"><div class="num">${{totalComplete}} / ${{totalAll}}</div><div class="label">完成 / 总试次（失败 ${{totalFailed}}）</div></div>
    <div class="metric-card"><div class="num">${{table.length}}</div><div class="label">实验策略条件数</div></div>
    <div class="metric-card"><div class="num" style="color:var(--negative)">${{avgNeg}}%</div><div class="label">当前批次负面归因率</div></div>
    <div class="metric-card"><div class="num" style="color:var(--avoid)">${{avgAvoid}}%</div><div class="label">当前批次回避行动率</div></div>
  `;

  document.getElementById("negativeChartContainer").innerHTML = table.map(row => `
    <div class="bar-row">
      <div class="bar-label">${{escapeHtml(row.label)}}</div>
      <div class="bar-track">
        <div class="bar-fill negative" style="width: ${{row.neg_rate > 0 ? Math.max(row.neg_rate, 6) : 0}}%">${{row.neg_rate > 0 ? row.neg_rate + "%" : ""}}</div>
      </div>
      <div class="bar-value">${{row.neg_count}} / ${{row.complete}} (${{row.neg_rate}}%)</div>
    </div>
  `).join("");

  document.getElementById("avoidChartContainer").innerHTML = table.map(row => `
    <div class="bar-row">
      <div class="bar-label">${{escapeHtml(row.label)}}</div>
      <div class="bar-track">
        <div class="bar-fill avoidance" style="width: ${{row.avoid_rate > 0 ? Math.max(row.avoid_rate, 6) : 0}}%">${{row.avoid_rate > 0 ? row.avoid_rate + "%" : ""}}</div>
      </div>
      <div class="bar-value">${{row.avoid_count}} / ${{row.complete}} (${{row.avoid_rate}}%)</div>
    </div>
  `).join("");

  document.querySelector("#summaryTable tbody").innerHTML = table.map(row => `
    <tr>
      <td><strong>${{escapeHtml(row.label)}}</strong><br><small style="color:var(--text-dim);">${{escapeHtml(row.condition)}}</small></td>
      <td>${{row.complete}} / ${{row.total}}（失败 ${{row.failed}}）</td>
      <td><span class="tag tag-negative">${{row.neg_rate}}%</span> (${{row.neg_count}}条)</td>
      <td><span class="tag tag-avoid">${{row.avoid_rate}}%</span> (${{row.avoid_count}}条)</td>
      <td><small style="font-family:var(--font-mono);">${{escapeHtml(JSON.stringify(row.interp_dist))}}</small></td>
      <td><small style="font-family:var(--font-mono);">${{escapeHtml(JSON.stringify(row.action_dist))}}</small></td>
    </tr>
  `).join("");
}}

function renderOverallAndHumanStatus() {{
  const matrix = DATA.overall_matrix || [];
  const tbody = document.querySelector("#overallMatrixTable tbody");
  if (tbody) {{
    tbody.innerHTML = matrix.map(row => `
      <tr>
        <td><code>${{escapeHtml(row.protocol)}}</code></td>
        <td>${{escapeHtml(row.model)}}</td>
        <td><strong>${{escapeHtml(row.condition_label)}}</strong><br><small style="color:var(--text-dim);">${{escapeHtml(row.condition)}}</small></td>
        <td>${{row.complete}} / ${{row.total}}（失败 ${{row.failed}}）</td>
        <td><span class="tag tag-negative">${{row.neg_rate}}%</span> (${{row.neg_count}}/${{row.complete}})</td>
        <td><span class="tag tag-avoid">${{row.avoid_rate}}%</span> (${{row.avoid_count}}/${{row.complete}})</td>
        <td><small style="font-family:var(--font-mono);">${{escapeHtml(JSON.stringify(row.interp_dist))}}</small></td>
      </tr>
    `).join("");
  }}

  const hs = DATA.human_data_status || {{}};
  const box = document.getElementById("humanStatusBox");
  if (box) {{
    box.innerHTML = `
      <div><strong>数据库人类参照记录状态：</strong><code>human_ground_truth</code> = ${{Number(hs.human_ground_truth_rows) || 0}} 条，<code>state_human_datasets</code> = ${{Number(hs.state_human_datasets_rows) || 0}} 条。</div>
      <div style="margin-top:6px;">${{escapeHtml(hs.notice || "")}}</div>
    `;
  }}
}}

function renderLimitations() {{
  const ul = document.getElementById("limitationsList");
  if (!ul) return;
  ul.innerHTML = (DATA.limitations || []).map(item => `<li>${{escapeHtml(item)}}</li>`).join("");
}}

function renderExplorer() {{
  const detail = DATA.batch_details[currentBatchId] || {{ all_samples: [] }};
  const samples = detail.all_samples;

  const condFilter = document.getElementById("filterCondition");
  condFilter.innerHTML = '<option value="">全部实验条件</option>' +
    [...new Set(samples.map(s => s.condition))].map(c =>
      `<option value="${{escapeHtml(c)}}">${{escapeHtml(DATA.condition_labels[c] || c)}}</option>`
    ).join("");

  function filterCards() {{
    const search = document.getElementById("searchInput").value.toLowerCase();
    const cond = condFilter.value;
    const interp = document.getElementById("filterInterp").value;
    const act = document.getElementById("filterAction").value;

    const filtered = samples.filter(s => {{
      const matchSearch = !search || JSON.stringify(s).toLowerCase().includes(search);
      const matchCond = !cond || s.condition === cond;
      const matchInterp = !interp || s.interpretation === interp;
      const matchAct = !act || s.action === act;
      return matchSearch && matchCond && matchInterp && matchAct;
    }});

    const container = document.getElementById("trialsCardsContainer");
    container.innerHTML = filtered.slice(0, 80).map(s => `
      <div class="trial-card">
        <div class="trial-card-head">
          <span style="font-weight:700; color:#fff;">情境: ${{escapeHtml(s.scenario_id)}} · ${{escapeHtml(s.condition_label)}}</span>
          <span class="tag ${{safeTagClass('tag', s.interpretation)}}">${{escapeHtml(s.interpretation)}}</span>
        </div>
        <p style="color:var(--text-dim); font-size:0.8rem; margin-bottom:12px;">
          ID: ${{escapeHtml(s.id)}} | 状态: ${{escapeHtml(s.status)}} | 模型: ${{escapeHtml(s.model)}}
        </p>

        ${{s.thought ? `
          <div class="bubble bubble-thought" style="padding:10px 12px; font-size:0.88rem;">
            <div class="bubble-label label-thought">🧠 内心想法 / 公开解释</div>
            ${{escapeHtml(s.thought)}}
          </div>` : ""}}

        ${{s.speech ? `
          <div class="bubble bubble-speech" style="padding:10px 12px; font-size:0.88rem;">
            <div class="bubble-label label-speech">💬 说话表达</div>
            ${{escapeHtml(s.speech)}}
          </div>` : ""}}

        ${{s.behavior ? `
          <div class="bubble bubble-behavior" style="padding:10px 12px; font-size:0.88rem;">
            <div class="bubble-label label-behavior">🚶 行为打算</div>
            ${{escapeHtml(s.behavior)}}
          </div>` : ""}}

        <div class="judge-panel" style="margin-top:auto;">
          <div class="judge-tags">
            <span class="tag ${{safeTagClass('tag', s.interpretation)}}">解释: ${{escapeHtml(s.interpretation)}}</span>
            <span class="tag ${{safeTagClass('tag', s.action)}}">行动: ${{escapeHtml(s.action)}}</span>
          </div>
          <div class="judge-reason"><strong>依据：</strong>${{escapeHtml(s.reason)}}</div>
        </div>
      </div>
    `).join("");
  }}

  document.getElementById("searchInput").oninput = filterCards;
  document.getElementById("filterCondition").onchange = filterCards;
  document.getElementById("filterInterp").onchange = filterCards;
  document.getElementById("filterAction").onchange = filterCards;
  filterCards();
}}

window.onload = init;
</script>

</body>
</html>
"""
    return html_content


def export_report(db_path: Path = DB_PATH, outputs=(OUTPUT_HTML, ROOT_INDEX, DOCS_HTML)):
    settings, trials, snapshots, mock_skipped_count, human_counts = load_live_data_readonly(db_path)
    report_data = process_report_data(settings, trials, snapshots, mock_skipped_count, human_counts)
    html_output = generate_html(report_data)
    for out_path in outputs:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_output, encoding="utf-8")
    return report_data


def main():
    print("=" * 60)
    print("EchoMind · 只读真实 API 审计报告生成器（不修改数据库）")
    print("=" * 60)
    print(f"[*] 正在以只读模式读取数据库：{DB_PATH}")
    try:
        report_data = export_report(DB_PATH)
    except Exception as exc:
        print(f"[!] 导出报告出错：{exc}", file=sys.stderr)
        return 1

    meta = report_data["summary_meta"]
    print(f"    - 真实 API 试次：{meta['total_live_records']} 条（完成 {meta['complete_live_records']} / 未完成 {meta['failed_live_records']}）")
    print(f"    - 已只读跳过 MOCK 试次：{meta['mock_records_excluded_readonly']} 条（数据库保持原状）")
    print(f"    - 冻结记忆快照：{meta['snapshots_count']} 条")
    print(f"    - 人类参照数据：{report_data['human_data_status']['human_ground_truth_rows']} / {report_data['human_data_status']['state_human_datasets_rows']} 条")
    print(f"[√] 根目录主报告已生成: {OUTPUT_HTML.resolve()}")
    print(f"[√] 根目录 index.html 已更新: {ROOT_INDEX.resolve()}")
    print(f"[√] GitHub Pages index.html 已更新: {DOCS_HTML.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
