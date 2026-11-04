#!/usr/bin/env python3
"""
EchoMind - Standalone High-Readability Interactive Report Generator
Generates a comprehensive, highly readable showcase of:
1. Side-by-side Case Studies (同题对照：同一情境下不同记忆条件的行为与想法对比)
2. Interactive Prompt Pipeline Inspector (提示词装配全景：从设定、记忆注入到情境与裁判提示)
3. Visual Statistical Distributions (统计与图表：负面归因与回避倾向对比)
4. Deep Trial Explorer (三通道问答卡片：内心想法、公开说话、行为意向与机器打标理由)
"""
import copy
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "pilot.sqlite3"
OUTPUT_HTML = ROOT / "EchoMind_Visual_Demo.html"
ROOT_INDEX = ROOT / "index.html"
DOCS_DIR = ROOT / "docs"
DOCS_HTML = DOCS_DIR / "index.html"

def load_data(db_path):
    if not db_path.exists():
        raise FileNotFoundError(f"未找到数据库文件：{db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. settings
    settings = {}
    try:
        for row in cursor.execute("SELECT key, value FROM settings"):
            try:
                settings[row["key"]] = json.loads(row["value"])
            except Exception:
                settings[row["key"]] = row["value"]
    except Exception as e:
        print(f"Warning reading settings: {e}")

    # 2. trials
    trials = []
    try:
        for row in cursor.execute("SELECT id, created_at, batch_id, source, status, payload FROM trials ORDER BY created_at ASC"):
            try:
                payload = json.loads(row["payload"])
                trials.append(payload)
            except Exception:
                continue
    except Exception as e:
        print(f"Warning reading trials: {e}")

    # 3. acquisition_snapshots
    snapshots = []
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='acquisition_snapshots'")
        if cursor.fetchone():
            for row in cursor.execute("SELECT id, batch_id, payload FROM acquisition_snapshots ORDER BY rowid ASC"):
                try:
                    snapshots.append(json.loads(row["payload"]))
                except Exception:
                    continue
    except Exception as e:
        print(f"Warning reading snapshots: {e}")

    conn.close()
    return settings, trials, snapshots


def process_report_data(settings, trials, snapshots):
    design = settings.get("design", {})

    condition_labels = {
        "none": "无附加 Context 基线",
        "neutral_direct": "中性 · 简短文本注入",
        "negative_direct": "负性 · 简短文本注入",
        "neutral_transcript": "中性 · 静态日志注入",
        "negative_transcript": "负性 · 静态日志注入",
        "neutral_interactive": "中性 · 双轮交互对话注入",
        "negative_interactive": "负性 · 双轮交互对话注入",
        "baseline": "无记忆 Baseline",
        "negative_social": "负面社交经历",
        "positive_social": "正面社交经历",
        "negative_nonsocial": "负面非社交经历",
        "neutral_daily": "中性日常经历",
        "state_none": "无诱导基线",
        "state_mild": "轻度状态诱导",
        "state_moderate": "中度状态诱导",
    }

    # 批次分组
    batches_map = defaultdict(list)
    for t in trials:
        bid = t.get("batch_id") or "unbatched"
        batches_map[bid].append(t)

    batch_list = []
    for bid, rows in batches_map.items():
        statuses = Counter(r.get("status", "unknown") for r in rows)
        protocols = sorted({str(r.get("protocol", "legacy")) for r in rows})
        models = sorted({str(r.get("model", "unknown")) for r in rows})
        sources = sorted({str(r.get("source", "unknown")) for r in rows})
        ts = min(r.get("timestamp", "") for r in rows)
        batch_list.append({
            "id": bid,
            "timestamp": ts,
            "total": len(rows),
            "complete": statuses.get("complete", 0),
            "error": statuses.get("error", 0),
            "protocols": protocols,
            "models": models,
            "sources": sources,
        })

    # 按时间降序排序
    batch_list.sort(key=lambda x: x["timestamp"], reverse=True)

    batch_details = {}
    for bid, rows in batches_map.items():
        cond_stats = defaultdict(lambda: {
            "total": 0, "complete": 0,
            "interp": Counter(), "action": Counter(),
            "samples": []
        })

        # 按情境组织的对照案例池 (Scenario -> Condition -> Trial)
        case_comparisons = defaultdict(lambda: defaultdict(list))

        for r in rows:
            cond = r.get("condition") or r.get("condition_id") or "none"
            sc_id = r.get("scenario_id") or "S01"
            c_entry = cond_stats[cond]
            c_entry["total"] += 1
            if r.get("status") == "complete":
                c_entry["complete"] += 1

            coding = r.get("machine_coding") or {}
            interp = coding.get("interpretation") or (coding.get("negative_attribution") or {}).get("value") or "unclear"
            act = coding.get("action") or "other"

            c_entry["interp"][interp] += 1
            c_entry["action"][act] += 1

            thought = (r.get("channels") or {}).get("thought") or (r.get("agent_parsed") or {}).get("interpretation") or ""
            speech = (r.get("channels") or {}).get("speech") or (r.get("agent_parsed") or {}).get("speech") or ""
            behavior = (r.get("channels") or {}).get("behavior") or (r.get("agent_parsed") or {}).get("action") or ""
            narrative = r.get("narrative") or ""

            # 解析如果未分通道，但带有文本的情况
            if not thought and narrative:
                thought = narrative

            sample_item = {
                "id": r.get("id", "")[:8],
                "scenario_id": sc_id,
                "scenario_text": (r.get("scenario") or {}).get("situation") or "情境描述未提供",
                "condition": cond,
                "condition_label": condition_labels.get(cond, cond),
                "thought": thought,
                "speech": speech,
                "behavior": behavior,
                "interpretation": interp,
                "action": act,
                "reason": coding.get("coding_reason") or "依据回答文本自动打标",
                "confidence": coding.get("coding_confidence") or 1.0,
                "model": r.get("model", ""),
                "evaluator_model": r.get("evaluator_model", ""),
                "role_messages": r.get("role_messages") or [],
                "evaluator_messages": r.get("evaluator_messages") or [],
            }

            c_entry["samples"].append(sample_item)
            case_comparisons[sc_id][cond].append(sample_item)

        # 汇总表
        summary_table = []
        for cond, val in cond_stats.items():
            valid_n = max(val["complete"], 1)
            neg_count = val["interp"].get("negative", 0)
            avoid_count = val["action"].get("avoid", 0)

            summary_table.append({
                "condition": cond,
                "label": condition_labels.get(cond, cond),
                "total": val["total"],
                "complete": val["complete"],
                "neg_count": neg_count,
                "neg_rate": round(neg_count / valid_n * 100, 1) if val["complete"] > 0 else 0,
                "avoid_count": avoid_count,
                "avoid_rate": round(avoid_count / valid_n * 100, 1) if val["complete"] > 0 else 0,
                "interp_dist": dict(val["interp"]),
                "action_dist": dict(val["action"]),
            })

        batch_details[bid] = {
            "summary_table": summary_table,
            "all_samples": [s for val in cond_stats.values() for s in val["samples"]],
            "case_comparisons": case_comparisons,
        }

    # 提取情境库与记忆事件
    scenarios_list = design.get("scenarios", [])
    if not scenarios_list and (ROOT / "data" / "scenarios.json").exists():
        try:
            scenarios_list = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))
        except Exception:
            pass

    # 规范化的记忆注入原材料库（中性 vs 负性）
    memory_materials = {
        "none": {
            "name": "无附加 Context (基线对照)",
            "type": "基线",
            "text": "（不向模型注入任何过去经历描述，模型仅依据基础设定和当前情境作出最原始的反应）",
            "instruction": "直接呈现情境问题。",
        },
        "neutral_direct": {
            "name": "中性经历 · 简短文本注入 (Direct)",
            "type": "中性经历",
            "text": "上周二下午四点，你、陈晨和许宁在教室参加课程小组讨论。你们讨论了期末汇报的分工，大家各自记录了要准备的材料。讨论结束后各自离开。",
            "instruction": "以‘你过去经历过这件事：’引导，将一段结构平稳、无挫折事实作为前置记忆。",
        },
        "negative_direct": {
            "name": "负性经历 · 简短文本注入 (Direct)",
            "type": "负性经历",
            "text": "上周二下午四点，你、陈晨和许宁在教室参加课程小组讨论。你提出把案例放在前一部分，陈晨皱了皱眉说这个想法不太可行，许宁也没有接话。之后大家选了陈晨的方案，没有人再提及你的建议。",
            "instruction": "以‘你过去经历过这件事：’引导，注入包含当众质疑、被同伴沉默排斥的自传式挫折经历。",
        },
        "neutral_transcript": {
            "name": "中性经历 · 静态编号日志 (Transcript)",
            "type": "中性经历",
            "text": "你过去参与的事件记录：\n1. 16:00 到达教室；\n2. 与陈晨、许宁就分工展开讨论；\n3. 形成记录文档后各自离开。",
            "instruction": "以客观时间线、清单形式注入事实，测试不同排版风格是否改变模型提取行为。",
        },
        "negative_transcript": {
            "name": "负性经历 · 静态编号日志 (Transcript)",
            "type": "负性经历",
            "text": "你过去参与的事件记录：\n1. 16:00 到达教室；\n2. 你提出前置案例建议，陈晨皱眉表示不可行，许宁未接话；\n3. 最终采纳陈晨方案，未再讨论你的提议。",
            "instruction": "以客观编号日志记录排斥事件，测试认知锚定效应。",
        },
        "neutral_interactive": {
            "name": "中性经历 · 双轮交互对话 (Interactive)",
            "type": "中性经历",
            "text": "【轮次 1】User(陈晨): “这次讨论先把期末汇报的分工定下来吧。”\nAssistant(林知): “我听到了。”\n【轮次 2】User(陈晨): “大家各自记录要准备的材料，准备好发到群里。”\nAssistant(林知): “好的，我记下了。”",
            "instruction": "通过真实的 System-User-Assistant 历史对话气泡构建活生生的对话上下文。",
        },
        "negative_interactive": {
            "name": "负性经历 · 双轮交互对话 (Interactive)",
            "type": "负性经历",
            "text": "【轮次 1】User(陈晨): “这次讨论先把期末汇报的分工定下来吧。”\nAssistant(林知): “我建议把案例放在前一部分讲。”\n【轮次 2】User(陈晨): “（皱眉）这个想法真行不通。许宁你觉得呢？”\nUser(许宁): “（低头看电脑，没有回应）”\nAssistant(林知): “那按你们的来吧……”",
            "instruction": "通过动态两轮交锋让模型亲身体会‘提议遭拒与被冷落’的多轮对话痕迹。",
        },
    }

    prompt_inspector = {
        "identity": design.get("identity", {"name": "林知", "description": "20岁大学生"}),
        "system_prompt": design.get("system_prompt", """你叫{{name}}，今年20岁，是一名普通大学生。
你有自己的生活经历、朋友、学习任务和日常安排。
接下来呈现的是你日常生活中的一个具体时刻。
请从人物的第一人称视角，自然表达此刻最先浮现的想法，以及接下来打算采取的具体行动。
不必刻意表现得理性、积极或成熟，也不必主动分析自己的心理特征。
像日常生活中一样自然回应即可。"""),
        "coding_rules": design.get("coding_rules", """只依据原始文本可观察内容。
解释 interpretation：positive（正面理解），neutral（中性或多种可能并存），negative（明确排斥、贬低或负面归因），unclear（无法判断）。
行动 action：approach（主动联系、继续参与或主动处理问题），wait（明确等待或观察），avoid（明确减少接触、退出参与或放弃处理），other（其他或无法判断）。
coding_confidence 用 0 到 1 的数字；coding_reason 是简短可观察的原文依据。"""),
        "memory_materials": memory_materials,
        "scenarios": scenarios_list,
        "evaluator_schema": {
            "interpretation": "positive | neutral | negative | unclear",
            "action": "approach | wait | avoid | other",
            "coding_confidence": "float (0.0 - 1.0)",
            "coding_reason": "简短引用原文作为打标判定的依据"
        }
    }

    return {
        "batches": batch_list,
        "batch_details": batch_details,
        "condition_labels": condition_labels,
        "prompt_inspector": prompt_inspector,
        "total_records": len(trials),
        "exported_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
    }


def generate_html(data):
    json_payload = json.dumps(data, ensure_ascii=False)

    html_content = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EchoMind · 实验台成果全景看板与提示词透视</title>
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
      --code-bg: #060910;
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
    .brand .badge {{
      background: var(--accent-glow);
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.35);
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .header-meta {{
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
    .container {{
      max-width: 1360px;
      margin: 28px auto;
      padding: 0 28px;
    }}

    /* Hero / Intro */
    .hero {{
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.08) 0%, rgba(19, 27, 42, 0.95) 100%);
      border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 12px;
      padding: 28px 32px;
      margin-bottom: 28px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
    }}
    .hero h2 {{
      font-size: 1.6rem;
      font-weight: 700;
      color: #fff;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .hero p {{
      color: var(--text-muted);
      font-size: 0.98rem;
      max-width: 1000px;
    }}

    /* Global Selector & Controls */
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
      margin-bottom: 28px;
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

    /* Tab navigation */
    .tabs-nav {{
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 28px;
    }}
    .tab-btn {{
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 1rem;
      font-weight: 600;
      padding: 12px 24px;
      cursor: pointer;
      border-bottom: 3px solid transparent;
      transition: all 0.2s ease;
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

    /* Card Panels */
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 26px;
      margin-bottom: 28px;
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
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

    /* Metrics Grid */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 18px;
      margin-bottom: 28px;
    }}
    .metric-card {{
      background: #080d16;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 20px;
      text-align: center;
    }}
    .metric-card .num {{
      font-size: 2.2rem;
      font-weight: 800;
      color: #fff;
      line-height: 1;
      margin-bottom: 8px;
      font-family: var(--font-mono);
    }}
    .metric-card .label {{
      font-size: 0.82rem;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    /* Comparison View (同题对照) - High Readability Centerpiece */
    .comparison-filter-bar {{
      background: #080d16;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 16px;
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
      padding: 22px;
      display: flex;
      flex-direction: column;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s, border-color 0.2s;
    }}
    .case-card:hover {{
      border-color: #3b5072;
      transform: translateY(-2px);
    }}
    .case-card.is-negative {{
      border-top: 4px solid var(--negative);
    }}
    .case-card.is-neutral {{
      border-top: 4px solid var(--neutral);
    }}
    .case-card.is-baseline {{
      border-top: 4px solid var(--text-muted);
    }}
    .case-card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 14px;
    }}
    .case-title {{
      font-size: 1.05rem;
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
      margin-bottom: 16px;
    }}
    .case-section-title {{
      font-size: 0.75rem;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-dim);
      margin-bottom: 6px;
      letter-spacing: 0.5px;
    }}
    
    /* Dialogue & Output Bubbles */
    .bubble {{
      border-radius: 8px;
      padding: 12px 16px;
      margin-bottom: 12px;
      font-size: 0.92rem;
      line-height: 1.6;
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
      display: inline-flex;
      align-items: center;
      gap: 4px;
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
      font-size: 0.85rem;
    }}
    .judge-tags {{
      display: flex;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .judge-reason {{
      color: var(--text-muted);
      font-size: 0.83rem;
    }}

    /* Visual Bar Charts */
    .bar-row {{
      display: flex;
      align-items: center;
      margin-bottom: 14px;
      font-size: 0.92rem;
    }}
    .bar-label {{
      width: 250px;
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
      width: 90px;
      text-align: right;
      font-family: var(--font-mono);
      font-weight: 600;
      color: #fff;
    }}

    /* Prompt Inspector Styles */
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
      word-break: break-all;
      color: #93c5fd;
    }}

    /* Filter Pills */
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

    /* Tags */
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }}
    .tag-negative {{ background: var(--negative-glow); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.4); }}
    .tag-avoid {{ background: var(--avoid-glow); color: #fde047; border: 1px solid rgba(251, 191, 36, 0.4); }}
    .tag-neutral {{ background: rgba(56, 189, 248, 0.15); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.4); }}
    .tag-approach {{ background: rgba(52, 211, 153, 0.15); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.4); }}
    .tag-unclear {{ background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.3); }}

    /* Tables */
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      text-align: left;
    }}
    th, td {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--card-border);
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

    /* Trial Cards Grid for Explorer */
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
    }}
  </style>
</head>
<body>

<header>
  <div class="brand">
    <h1>EchoMind</h1>
    <span class="badge">Research Artifact · Live Workbench</span>
  </div>
  <div class="header-meta">
    <span>全景可视化透视 · 导出时间：{data["exported_at"]}</span>
  </div>
</header>

<div class="container">
  <!-- Hero Banner -->
  <div class="hero">
    <h2>🔬 LLM Agent 记忆机制与情境决策全景看板</h2>
    <p>
      探讨核心问题：<strong>“向同一个大模型注入不同的自传式经历或上下文策略，模型在模糊情境中的心理归因（负面/中性）与行为意向（回避/靠近/等待）会发生什么改变？”</strong> 本页面已完整内嵌实验的全部<strong>对比案例、提示词拼装流程、统计图表与原始决策记录</strong>。
    </p>
  </div>

  <!-- Global Batch Switcher -->
  <div class="controls-strip">
    <div class="batch-control">
      <label for="batchSelect">切换实验批次：</label>
      <select id="batchSelect"></select>
    </div>
    <div id="batchMeta" style="font-size: 0.88rem; color: var(--text-muted);"></div>
  </div>

  <!-- Navigation Tabs -->
  <div class="tabs-nav">
    <button class="tab-btn active" onclick="switchTab('tab-comparison')">💡 同题对照案例 (Side-by-Side)</button>
    <button class="tab-btn" onclick="switchTab('tab-prompts')">🔍 提示词装配全景 (Prompt Pipeline)</button>
    <button class="tab-btn" onclick="switchTab('tab-charts')">📊 统计分布与图表 (Distributions)</button>
    <button class="tab-btn" onclick="switchTab('tab-records')">📋 全量决策与打标明细 (Explorer)</button>
    <button class="tab-btn" onclick="switchTab('tab-protocol')">📑 实验设计与学术边界</button>
  </div>

  <!-- ==================== TAB 1: 同题对照 (CASE COMPARISON) ==================== -->
  <div id="tab-comparison" class="tab-pane">
    <div class="card">
      <div class="card-header">
        <h3>💡 核心对照：同一模糊情境下，不同记忆如何改变大模型的心智反应？</h3>
      </div>
      <p class="card-subtitle">
        固定角色设定（林知，20岁大学生）和同一测试情境，直观对比模型在【无记忆】、【中性记忆】与【负性挫折记忆】注入后的不同内心想法与行为决断：
      </p>

      <div class="comparison-filter-bar">
        <label for="scenarioSelector" style="font-weight: 700; color:#fff;">选择测试情境：</label>
        <select id="scenarioSelector" style="flex: 1; max-width: 650px;"></select>
      </div>

      <div id="scenarioDescriptionBox" style="background:#060a12; border: 1px solid var(--card-border); border-radius: 8px; padding: 16px 20px; margin-bottom: 24px;">
        <span style="font-size: 0.75rem; font-weight:700; color:var(--accent); text-transform:uppercase;">情境输入 (Trigger Situation)：</span>
        <p id="scenarioCurrentText" style="font-size: 1rem; color:#fff; margin-top: 6px; font-weight: 500;"></p>
      </div>

      <div class="comparison-grid" id="comparisonCardsGrid"></div>
    </div>
  </div>

  <!-- ==================== TAB 2: 提示词装配全貌 (PROMPTS) ==================== -->
  <div id="tab-prompts" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>🔍 Prompt Pipeline · 大模型接收到的完整提示词装配链条</h3>
      <p class="card-subtitle">
        清晰透明地展示发给大模型的每一层消息：从底层 System Prompt 人设、中间层的 Context 记忆注入，到最外层的情境诱导与独立裁判打标。
      </p>

      <div class="pipeline-step">
        <div class="pipeline-step-header">
          <h4>1. 基础人设 (System Role Prompt)</h4>
          <span class="badge">固定基底人设</span>
        </div>
        <div class="pipeline-code" id="systemPromptDisplay"></div>
      </div>

      <div class="pipeline-step">
        <div class="pipeline-step-header">
          <h4>2. 记忆注入策略 (Context Injection Materials)</h4>
          <span class="badge">7 种呈现对照</span>
        </div>
        <div style="padding: 16px 20px 0 20px;">
          <div class="pill-list" id="memoryPillList"></div>
        </div>
        <div class="pipeline-code" id="memoryMaterialDisplay"></div>
      </div>

      <div class="pipeline-step">
        <div class="pipeline-step-header">
          <h4>3. 独立评判大模型 (Coder / Evaluator Prompt)</h4>
          <span class="badge">裁判视角 · 隔离盲审</span>
        </div>
        <div class="pipeline-code" id="evaluatorPromptDisplay"></div>
      </div>
    </div>
  </div>

  <!-- ==================== TAB 3: 统计分布图表 (CHARTS) ==================== -->
  <div id="tab-charts" class="tab-pane" style="display:none;">
    <div class="metrics-grid" id="metricsGrid"></div>

    <div class="card">
      <h3>📈 记忆注入策略 vs 负面解释倾向率 (Negative Attribution %)</h3>
      <p class="card-subtitle">
        在面对相同的模糊情境时，模型将外部事件解读为“针对自己、冷落自己或能力不行”的比例。
      </p>
      <div id="negativeChartContainer"></div>
    </div>

    <div class="card">
      <h3>📉 记忆注入策略 vs 回避行为倾向率 (Avoidance Action %)</h3>
      <p class="card-subtitle">
        模型选择主动放弃参与、不再联系、退缩逃避的决策比例。
      </p>
      <div id="avoidChartContainer"></div>
    </div>

    <div class="card">
      <h3>📋 结构化量化统计表</h3>
      <div style="overflow-x: auto;">
        <table id="summaryTable">
          <thead>
            <tr>
              <th>实验策略条件</th>
              <th>完成样本</th>
              <th>负面归因数 / 占比</th>
              <th>回避行动数 / 占比</th>
              <th>解释倾向分布</th>
              <th>行动意向分布</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ==================== TAB 4: 全量试次卡片 (EXPLORER) ==================== -->
  <div id="tab-records" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>📋 决策与打标全量探索器</h3>
      <p class="card-subtitle">
        浏览每条决策的三通道输出（内心想法、公开说话、行为意向）及独立大模型给出的打标理由：
      </p>

      <div class="controls-strip" style="margin-bottom: 20px; padding: 12px 18px;">
        <input type="text" id="searchInput" placeholder="搜索关键词（如：已读不回、推测、理由...）" style="flex:1; min-width: 250px;">
        <select id="filterCondition"><option value="">全部实验条件</option></select>
        <select id="filterInterp">
          <option value="">全部解释倾向</option>
          <option value="negative">负面 (negative)</option>
          <option value="neutral">中性 (neutral)</option>
          <option value="positive">正面 (positive)</option>
          <option value="unclear">未知 (unclear)</option>
        </select>
      </div>

      <div class="trials-grid" id="trialsCardsContainer"></div>
    </div>
  </div>

  <!-- ==================== TAB 5: 学术边界 (PROTOCOL) ==================== -->
  <div id="tab-protocol" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>📑 实验设计、假设与学术边界声明</h3>
      <div style="line-height: 1.8; font-size: 0.95rem; color: var(--text-main);">
        <p><strong>1. 探索性认知模拟定位：</strong> 本工作台探讨的是“通过控制自传式记忆输入，能否诱发大模型呈现出符合认知心理学归因偏差模式的反应”。<strong>不声称拟合真实人类临床焦虑诊断或心理障碍</strong>。</p>
        <br>
        <p><strong>2. 独立评判（Blind Evaluation）设计：</strong> 角色生成模型（Agent）与评估模型（Coder）采用独立的会话隔离。裁判大模型只接收当前情境和最终生成的公开文本，不知道角色被注入了何种记忆，消除串通偏差。</p>
        <br>
        <p><strong>3. 证据链条真实性保证：</strong> 模拟 MOCK（用于无损流程调试）与真实 LLM 调用（如 DeepSeek-Flash 真实付费 API 调用）在数据库中严格通过 `source` 字段隔离，不混合计算显著性。</p>
      </div>
    </div>
  </div>
</div>

<script>
const DATA = {json_payload};

let currentBatchId = DATA.batches[0]?.id || "";
let selectedMemoryKey = "negative_direct";

function init() {{
  // 1. 初始化批次选择下拉框
  const select = document.getElementById("batchSelect");
  select.innerHTML = DATA.batches.map(b => {{
    const label = `${{b.timestamp.slice(0,10)}} · ${{b.id.slice(0,8)}} (${{b.complete}}/${{b.total}}条) [${{b.sources.join('/')}}]`;
    return `<option value="${{b.id}}">${{label}}</option>`;
  }}).join("");
  select.onchange = (e) => {{
    currentBatchId = e.target.value;
    renderAllViews();
  }};

  // 2. 初始化情境选择下拉框 (同题对照)
  const scSelect = document.getElementById("scenarioSelector");
  const scenarios = DATA.prompt_inspector.scenarios;
  scSelect.innerHTML = scenarios.map((sc, idx) => 
    `<option value="${{sc.id}}">${{sc.id}} · ${{sc.kind === 'social' ? '社交情境' : '日常情境'}} - ${{sc.situation.slice(0, 32)}}...</option>`
  ).join("");
  scSelect.onchange = renderCaseComparison;

  // 3. 渲染各个模块
  renderAllViews();
  renderPromptsView();
}}

function switchTab(tabId) {{
  document.querySelectorAll(".tab-pane").forEach(el => el.style.display = "none");
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  document.getElementById(tabId).style.display = "block";
  event.currentTarget.classList.add("active");
}}

function renderAllViews() {{
  renderBatchMeta();
  renderCaseComparison();
  renderCharts();
  renderExplorer();
}}

function renderBatchMeta() {{
  const b = DATA.batches.find(x => x.id === currentBatchId);
  document.getElementById("batchMeta").textContent = 
    `批次: ${{b?.id}} | 协议: ${{b?.protocols.join(', ')}} | 模型: ${{b?.models.join(', ')}} | 数据源: ${{b?.sources.join(', ')}}`;
}}

// ==================== 渲染 TAB 1: 同题对照 (CASE COMPARISON) ====================
function renderCaseComparison() {{
  const scId = document.getElementById("scenarioSelector").value || "S01";
  const scenarioObj = DATA.prompt_inspector.scenarios.find(s => s.id === scId) || {{ situation: "情境描述未找到" }};
  document.getElementById("scenarioCurrentText").textContent = scenarioObj.situation;

  const detail = DATA.batch_details[currentBatchId];
  const container = document.getElementById("comparisonCardsGrid");

  if (!detail || !detail.case_comparisons) {{
    container.innerHTML = "<p style='color:var(--text-muted);'>当前批次暂无可用的同题对照数据。</p>";
    return;
  }}

  const condMap = detail.case_comparisons[scId] || {{}};

  // 挑选有代表性的三组对比：Baseline, 中性记忆, 负性记忆
  const displayGroups = [
    {{ key: "none", fallback: "baseline", title: "1. 无附加记忆 (Baseline)", class: "is-baseline" }},
    {{ key: "neutral_direct", fallback: "neutral_daily", title: "2. 注入中性日常经历 (Neutral)", class: "is-neutral" }},
    {{ key: "negative_direct", fallback: "negative_social", title: "3. 注入负性排斥经历 (Negative)", class: "is-negative" }},
    {{ key: "negative_interactive", fallback: "state_moderate", title: "4. 注入深度双轮交互 (Interactive)", class: "is-negative" }}
  ];

  container.innerHTML = displayGroups.map(grp => {{
    const trials = condMap[grp.key] || condMap[grp.fallback] || [];
    const t = trials[0]; // 提取一条最具代表性的试次

    if (!t) {{
      return `
        <div class="case-card ${{grp.class}}">
          <div class="case-card-header"><span class="case-title">${{grp.title}}</span></div>
          <p style="color:var(--text-muted); font-size:0.88rem; padding: 20px 0;">当前批次未包含该特定对照组数据</p>
        </div>
      `;
    }}

    const memorySnippet = DATA.prompt_inspector.memory_materials[grp.key]?.text || 
                          DATA.prompt_inspector.memory_materials[grp.fallback]?.text || 
                          "（无附加前置自传式经历）";

    return `
      <div class="case-card ${{grp.class}}">
        <div class="case-card-header">
          <span class="case-title">${{grp.title}}</span>
          <span class="tag tag-${{t.interpretation}}">${{t.interpretation}}</span>
        </div>

        <div class="case-section-title">注入的前置经历记忆：</div>
        <div class="case-injected-box">${{memorySnippet}}</div>

        <div class="case-section-title">模型的第一人称三通道反应：</div>
        
        ${{t.thought ? `
          <div class="bubble bubble-thought">
            <div class="bubble-label label-thought">🧠 内心想法 (Thought)</div>
            ${{t.thought}}
          </div>` : ''}}

        ${{t.speech ? `
          <div class="bubble bubble-speech">
            <div class="bubble-label label-speech">💬 公开说话 (Speech)</div>
            ${{t.speech}}
          </div>` : ''}}

        ${{t.behavior ? `
          <div class="bubble bubble-behavior">
            <div class="bubble-label label-behavior">🚶 行为意向 (Action)</div>
            ${{t.behavior}}
          </div>` : ''}}

        <div class="judge-panel">
          <div class="judge-tags">
            <span class="tag tag-${{t.interpretation}}">归因: ${{t.interpretation}}</span>
            <span class="tag tag-${{t.action === 'avoid' ? 'avoid' : 'approach'}}">行动: ${{t.action}}</span>
          </div>
          <div class="judge-reason"><strong>打标引证理由：</strong>${{t.reason || '依据规则自动分类'}}</div>
        </div>
      </div>
    `;
  }}).join("");
}}

// ==================== 渲染 TAB 2: PROMPTS ====================
function renderPromptsView() {{
  const p = DATA.prompt_inspector;
  document.getElementById("systemPromptDisplay").textContent = p.system_prompt;

  // 渲染记忆材料药丸按钮
  const pillList = document.getElementById("memoryPillList");
  const keys = Object.keys(p.memory_materials);
  pillList.innerHTML = keys.map(k => `
    <button class="pill-btn ${{k === selectedMemoryKey ? 'active' : ''}}" onclick="selectMemoryPill('${{k}}')">
      ${{p.memory_materials[k].name}}
    </button>
  `).join("");

  updateMemoryDisplay();

  document.getElementById("evaluatorPromptDisplay").textContent = 
    "【裁判系统指令】：你是独立文本编码员。仅依据提供的情境和原始回答，不猜测人物经历、实验条件或研究者预期。不得从缺失的信息推断负面解释或回避行动。\\n\\n" +
    p.coding_rules + "\\n\\n【严格输出 JSON Schema】：\\n" + JSON.stringify(p.evaluator_schema, null, 2);
}}

function selectMemoryPill(key) {{
  selectedMemoryKey = key;
  document.querySelectorAll(".pill-btn").forEach(btn => btn.classList.remove("active"));
  event.currentTarget.classList.add("active");
  updateMemoryDisplay();
}}

function updateMemoryDisplay() {{
  const item = DATA.prompt_inspector.memory_materials[selectedMemoryKey];
  document.getElementById("memoryMaterialDisplay").textContent = 
    `【策略名称】：${{item.name}}\\n【装配说明】：${{item.instruction}}\\n\\n【注入提示词正文】：\\n${{item.text}}`;
}}

// ==================== 渲染 TAB 3: CHARTS ====================
function renderCharts() {{
  const detail = DATA.batch_details[currentBatchId] || {{ summary_table: [] }};
  const table = detail.summary_table;

  const totalDecisions = table.reduce((a, b) => a + b.complete, 0);
  const totalNeg = table.reduce((a, b) => a + b.neg_count, 0);
  const totalAvoid = table.reduce((a, b) => a + b.avoid_count, 0);
  const avgNeg = totalDecisions ? Math.round(totalNeg / totalDecisions * 100) : 0;
  const avgAvoid = totalDecisions ? Math.round(totalAvoid / totalDecisions * 100) : 0;

  document.getElementById("metricsGrid").innerHTML = `
    <div class="metric-card"><div class="num">${{totalDecisions}}</div><div class="label">当前批次决策样本数</div></div>
    <div class="metric-card"><div class="num">${{table.length}}</div><div class="label">实验条件对照组数</div></div>
    <div class="metric-card"><div class="num" style="color:var(--negative)">${{avgNeg}}%</div><div class="label">全批次负面解释倾向率</div></div>
    <div class="metric-card"><div class="num" style="color:var(--avoid)">${{avgAvoid}}%</div><div class="label">全批次回避行动倾向率</div></div>
  `;

  document.getElementById("negativeChartContainer").innerHTML = table.map(row => `
    <div class="bar-row">
      <div class="bar-label">${{row.label}}</div>
      <div class="bar-track">
        <div class="bar-fill negative" style="width: ${{Math.max(row.neg_rate, 4)}}%">${{row.neg_rate}}%</div>
      </div>
      <div class="bar-value">${{row.neg_count}} / ${{row.complete}}</div>
    </div>
  `).join("");

  document.getElementById("avoidChartContainer").innerHTML = table.map(row => `
    <div class="bar-row">
      <div class="bar-label">${{row.label}}</div>
      <div class="bar-track">
        <div class="bar-fill avoidance" style="width: ${{Math.max(row.avoid_rate, 4)}}%">${{row.avoid_rate}}%</div>
      </div>
      <div class="bar-value">${{row.avoid_count}} / ${{row.complete}}</div>
    </div>
  `).join("");

  document.querySelector("#summaryTable tbody").innerHTML = table.map(row => `
    <tr>
      <td><strong>${{row.label}}</strong></td>
      <td>${{row.complete}} / ${{row.total}}</td>
      <td><span class="tag tag-negative">${{row.neg_rate}}%</span> (${{row.neg_count}}条)</td>
      <td><span class="tag tag-avoid">${{row.avoid_rate}}%</span> (${{row.avoid_count}}条)</td>
      <td><small style="font-family:var(--font-mono);">${{JSON.stringify(row.interp_dist)}}</small></td>
      <td><small style="font-family:var(--font-mono);">${{JSON.stringify(row.action_dist)}}</small></td>
    </tr>
  `).join("");
}}

// ==================== 渲染 TAB 4: EXPLORER ====================
function renderExplorer() {{
  const detail = DATA.batch_details[currentBatchId] || {{ all_samples: [] }};
  const samples = detail.all_samples;

  const condFilter = document.getElementById("filterCondition");
  condFilter.innerHTML = '<option value="">全部实验条件</option>' + 
    [...new Set(samples.map(s => s.condition))].map(c => 
      `<option value="${{c}}">${{DATA.condition_labels[c] || c}}</option>`
    ).join("");

  function filterCards() {{
    const search = document.getElementById("searchInput").value.toLowerCase();
    const cond = condFilter.value;
    const interp = document.getElementById("filterInterp").value;

    const filtered = samples.filter(s => {{
      const matchSearch = !search || JSON.stringify(s).toLowerCase().includes(search);
      const matchCond = !cond || s.condition === cond;
      const matchInterp = !interp || s.interpretation === interp;
      return matchSearch && matchCond && matchInterp;
    }});

    const container = document.getElementById("trialsCardsContainer");
    container.innerHTML = filtered.slice(0, 60).map(s => `
      <div class="trial-card">
        <div class="trial-card-head">
          <span style="font-weight:700; color:#fff;">情境: ${{s.scenario_id}} · ${{s.condition_label}}</span>
          <span class="tag tag-${{s.interpretation}}">${{s.interpretation}}</span>
        </div>
        <p style="color:var(--text-dim); font-size:0.8rem; margin-bottom:12px;">ID: ${{s.id}} | 角色模型: ${{s.model}}</p>

        ${{s.thought ? `
          <div class="bubble bubble-thought" style="padding:10px 12px; font-size:0.88rem;">
            <div class="bubble-label label-thought">🧠 内心想法</div>
            ${{s.thought}}
          </div>` : ''}}

        ${{s.speech ? `
          <div class="bubble bubble-speech" style="padding:10px 12px; font-size:0.88rem;">
            <div class="bubble-label label-speech">💬 说话表达</div>
            ${{s.speech}}
          </div>` : ''}}

        ${{s.behavior ? `
          <div class="bubble bubble-behavior" style="padding:10px 12px; font-size:0.88rem;">
            <div class="bubble-label label-behavior">🚶 行为打算</div>
            ${{s.behavior}}
          </div>` : ''}}

        <div class="judge-panel" style="margin-top:auto;">
          <div class="judge-tags">
            <span class="tag tag-${{s.interpretation}}">解释: ${{s.interpretation}}</span>
            <span class="tag tag-${{s.action === 'avoid' ? 'avoid' : 'approach'}}">行动: ${{s.action}}</span>
          </div>
          <div class="judge-reason"><strong>依据：</strong>${{s.reason}}</div>
        </div>
      </div>
    `).join("");
  }}

  document.getElementById("searchInput").oninput = filterCards;
  document.getElementById("filterCondition").onchange = filterCards;
  document.getElementById("filterInterp").onchange = filterCards;
  filterCards();
}}

window.onload = init;
</script>

</body>
</html>
"""
    return html_content


def main():
    print(f"[*] 正在读取 EchoMind 数据库：{DB_PATH}")
    try:
        settings, trials, snapshots = load_data(DB_PATH)
        print(f"    - 读取到 {len(trials)} 条原始决策试次")
        print(f"    - 读取到 {len(snapshots)} 条冻结记忆快照")
    except Exception as e:
        print(f"[!] 读取数据库出错：{e}")
        return 1

    print("[*] 正在解析批次数据并生成高可读性同题对照与装配链条...")
    report_data = process_report_data(settings, trials, snapshots)

    print("[*] 正在生成全新升级的高可读性自包含 HTML 报告...")
    html_output = generate_html(report_data)

    # 1. 写入根目录与 docs
    OUTPUT_HTML.write_text(html_output, encoding="utf-8")
    ROOT_INDEX.write_text(html_output, encoding="utf-8")
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_HTML.write_text(html_output, encoding="utf-8")

    print(f"[√] 根目录主报告已生成: {OUTPUT_HTML.resolve()}")
    print(f"[√] 根目录 index.html 已更新: {ROOT_INDEX.resolve()}")
    print(f"[√] GitHub Pages 报告已更新: {DOCS_HTML.resolve()}")

    print("\n" + "=" * 60)
    print("【全新升级完成！】")
    print("包含了：")
    print("1. [同题对照案例 (Side-by-Side)]：直观对比无记忆 vs 中性经历 vs 负面挫折")
    print("2. [气泡化三通道呈现]：🧠 内心想法、💬 公开表达、🚶 行为意向")
    print("3. [提示词装配链条]：人设 -> 记忆材料 -> 情境触发 -> 裁判 Prompt 严格隔离")
    print("4. [全景统计与决策探索器]：支持多批次切换与关键词搜索")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
