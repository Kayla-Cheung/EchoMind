#!/usr/bin/env python3
"""
EchoMind - Standalone Interactive Report Generator
Extracts results, prompt templates, and trial records from SQLite database
and compiles them into a self-contained, offline-ready HTML visualization report.
Zero external dependencies required.
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

    # 1. 读取 settings
    settings = {}
    try:
        for row in cursor.execute("SELECT key, value FROM settings"):
            try:
                settings[row["key"]] = json.loads(row["value"])
            except Exception:
                settings[row["key"]] = row["value"]
    except Exception as e:
        print(f"Warning reading settings: {e}")

    # 2. 读取 trials
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

    # 3. 读取 acquisition_snapshots (如果存在)
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

    # 批次分组
    batches_map = defaultdict(list)
    for t in trials:
        bid = t.get("batch_id") or "unbatched"
        batches_map[bid].append(t)

    # 整理批次摘要
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

    # 提取 Demo 2 的规范材料与条件
    condition_labels = {
        "none": "无附加 Context 基线",
        "neutral_direct": "中性 · 简短文本注入",
        "negative_direct": "负性 · 简短文本注入",
        "neutral_transcript": "中性 · 静态记录注入",
        "negative_transcript": "负性 · 静态记录注入",
        "neutral_interactive": "中性 · 固定事件对话注入",
        "negative_interactive": "负性 · 固定事件对话注入",
        "baseline": "无记忆 Baseline",
        "negative_social": "负面社交经历",
        "positive_social": "正面社交经历",
        "negative_nonsocial": "负面非社交经历",
        "neutral_daily": "中性日常经历",
    }

    # 整理各批次的统计指标
    batch_details = {}
    for bid, rows in batches_map.items():
        # 统计条件分布
        cond_stats = defaultdict(lambda: {
            "total": 0, "complete": 0,
            "interp": Counter(), "action": Counter(),
            "samples": []
        })

        for r in rows:
            cond = r.get("condition") or r.get("condition_id") or "none"
            c_entry = cond_stats[cond]
            c_entry["total"] += 1
            if r.get("status") == "complete":
                c_entry["complete"] += 1

            # 编码提取
            coding = r.get("machine_coding") or {}
            interp = coding.get("interpretation") or (coding.get("negative_attribution") or {}).get("value") or "unclear"
            act = coding.get("action") or "other"

            c_entry["interp"][interp] += 1
            c_entry["action"][act] += 1

            # 挑选有代表性的样例展示
            c_entry["samples"].append({
                "id": r.get("id", "")[:8],
                "scenario_id": r.get("scenario_id", ""),
                "scenario_text": (r.get("scenario") or {}).get("situation") or "",
                "narrative": r.get("narrative") or "",
                "thought": (r.get("channels") or {}).get("thought") or (r.get("agent_parsed") or {}).get("interpretation") or "",
                "speech": (r.get("channels") or {}).get("speech") or (r.get("agent_parsed") or {}).get("speech") or "",
                "behavior": (r.get("channels") or {}).get("behavior") or (r.get("agent_parsed") or {}).get("action") or "",
                "interpretation": interp,
                "action": act,
                "reason": coding.get("coding_reason") or "",
                "confidence": coding.get("coding_confidence") or 1.0,
                "model": r.get("model", ""),
                "evaluator_model": r.get("evaluator_model", ""),
            })

        # 转换为图表可用的百分比数组
        summary_table = []
        for cond, val in cond_stats.items():
            valid_n = max(val["complete"], 1)
            neg_count = val["interp"].get("negative", 0)
            avoid_count = val["action"].get("avoid", 0)
            neu_count = val["interp"].get("neutral", 0) + val["interp"].get("positive", 0)
            app_count = val["action"].get("approach", 0) + val["action"].get("wait", 0)

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
                "samples": val["samples"][:8],  # 每个条件提取前8条供直观审查
            })

        batch_details[bid] = {
            "summary_table": summary_table,
            "all_samples": [s for val in cond_stats.values() for s in val["samples"]],
        }

    # 提取代表性的 Prompt 提示词结构
    sample_trial = trials[-1] if trials else {}
    sample_role_messages = sample_trial.get("role_messages") or []
    sample_eval_messages = sample_trial.get("evaluator_messages") or []

    prompt_inspector = {
        "identity": design.get("identity", {"name": "林知", "description": "20岁大学生"}),
        "system_prompt": design.get("system_prompt", "你叫{{name}}，今年20岁，是一名普通大学生..."),
        "coding_rules": design.get("coding_rules", "只依据原始文本可观察内容..."),
        "role_messages_example": sample_role_messages,
        "evaluator_messages_example": sample_eval_messages,
        "scenarios": design.get("scenarios", [])[:4],
        "events_library": {
            "neutral": {
                "direct": "上周二下午四点，你、陈晨和许宁在教室参加课程小组讨论。你们讨论了期末汇报的分工，大家各自记录了要准备的材料。",
                "transcript": "1. 16:00 到达教室；2. 与陈晨、许宁就分工展开讨论；3. 形成记录文档后各自离开。",
                "interactive": "你听到陈晨说：“这部分按刚才说的办，大家先分别准备吧。”你回应：“好，我记下了。”",
            },
            "negative": {
                "direct": "上周二下午四点，你、陈晨和许宁在教室参加课程小组讨论。你提出把案例放在前一部分，陈晨皱了皱眉说这个想法不太可行，许宁也没有接话。之后大家选了陈晨的方案，没人再提及你的建议。",
                "transcript": "1. 16:00 到达教室；2. 你提出前置案例建议，陈晨皱眉表示不可行，许宁未回应；3. 采纳陈晨方案，未再讨论你的提议。",
                "interactive": "你提出建议后，陈晨直视你说：“这个想法真行不通。”许宁默默看电脑没有说话。你回应：“那按你的来吧。”",
            }
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
  <title>EchoMind · 记忆与行为实验结果与提示词全景展示</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-border: #30363d;
      --text-main: #c9d1d9;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --accent-hover: #79c0ff;
      --danger: #f85149;
      --success: #3fb950;
      --warning: #d29922;
      --code-bg: #090d13;
      --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text-main);
      line-height: 1.5;
      padding-bottom: 60px;
    }}
    header {{
      background: #010409;
      border-bottom: 1px solid var(--card-border);
      padding: 18px 32px;
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
      gap: 12px;
    }}
    .brand h1 {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #fff;
    }}
    .brand .badge {{
      background: rgba(88, 166, 255, 0.15);
      color: var(--accent);
      border: 1px solid rgba(88, 166, 255, 0.3);
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
    }}
    .header-meta {{
      font-size: 0.825rem;
      color: var(--text-muted);
    }}
    .container {{
      max-width: 1280px;
      margin: 24px auto;
      padding: 0 24px;
    }}
    .intro-banner {{
      background: linear-gradient(135deg, rgba(31, 111, 235, 0.12), rgba(22, 27, 34, 0.8));
      border: 1px solid #1f6feb44;
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .intro-banner h2 {{
      font-size: 1.4rem;
      color: #fff;
      margin-bottom: 8px;
    }}
    .intro-banner p {{
      color: var(--text-muted);
      font-size: 0.95rem;
    }}

    /* Controls Bar */
    .controls-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 16px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 24px;
    }}
    .batch-selector {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .batch-selector label {{
      font-weight: 600;
      font-size: 0.9rem;
      color: #fff;
    }}
    select {{
      background: #0d1117;
      border: 1px solid var(--card-border);
      color: var(--text-main);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.875rem;
      outline: none;
    }}
    select:focus {{ border-color: var(--accent); }}

    /* Tab navigation */
    .tabs {{
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 24px;
    }}
    .tab-btn {{
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 0.95rem;
      font-weight: 600;
      padding: 10px 18px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s;
    }}
    .tab-btn:hover {{ color: var(--text-main); }}
    .tab-btn.active {{
      color: var(--accent);
      border-bottom-color: var(--accent);
    }}

    /* Card Panels */
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .card h3 {{
      font-size: 1.15rem;
      color: #fff;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    /* Metrics Grid */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric-card {{
      background: #0d1117;
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 16px;
      text-align: center;
    }}
    .metric-card .num {{
      font-size: 2rem;
      font-weight: 700;
      color: #fff;
      line-height: 1.1;
      margin-bottom: 6px;
    }}
    .metric-card .label {{
      font-size: 0.8rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    /* Charts & Visual Bars */
    .chart-box {{
      margin-bottom: 24px;
    }}
    .bar-row {{
      display: flex;
      align-items: center;
      margin-bottom: 12px;
      font-size: 0.875rem;
    }}
    .bar-label {{
      width: 220px;
      flex-shrink: 0;
      color: var(--text-main);
      font-weight: 500;
    }}
    .bar-track {{
      flex: 1;
      height: 28px;
      background: #0d1117;
      border-radius: 4px;
      overflow: hidden;
      display: flex;
      border: 1px solid #30363d66;
      margin: 0 16px;
      position: relative;
    }}
    .bar-fill {{
      height: 100%;
      transition: width 0.4s ease;
      display: flex;
      align-items: center;
      padding-left: 8px;
      font-size: 0.75rem;
      font-weight: 600;
      color: #fff;
      white-space: nowrap;
    }}
    .bar-fill.negative {{ background: #f85149dd; }}
    .bar-fill.avoidance {{ background: #d29922dd; }}
    .bar-value {{
      width: 80px;
      text-align: right;
      font-family: var(--font-mono);
      font-weight: 600;
      color: #fff;
    }}

    /* Table */
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
      text-align: left;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--card-border);
    }}
    th {{
      background: #0d1117;
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.75rem;
      letter-spacing: 0.5px;
    }}
    tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}

    /* Prompt Inspector Styles */
    .prompt-block {{
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 16px;
      margin-bottom: 16px;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      white-space: pre-wrap;
      word-break: break-all;
      color: #79c0ff;
    }}
    details {{
      background: #0d1117;
      border: 1px solid var(--card-border);
      border-radius: 6px;
      margin-bottom: 12px;
      padding: 12px 16px;
    }}
    summary {{
      font-weight: 600;
      cursor: pointer;
      color: #fff;
      outline: none;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    summary:hover {{ color: var(--accent); }}
    .details-content {{
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid #30363d66;
    }}

    /* Tags & Pills */
    .tag {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
    }}
    .tag-negative {{ background: rgba(248, 81, 73, 0.2); color: #ff7b72; border: 1px solid rgba(248, 81, 73, 0.4); }}
    .tag-avoid {{ background: rgba(210, 153, 34, 0.2); color: #d29922; border: 1px solid rgba(210, 153, 34, 0.4); }}
    .tag-neutral {{ background: rgba(56, 139, 253, 0.2); color: #79c0ff; border: 1px solid rgba(56, 139, 253, 0.4); }}
    .tag-approach {{ background: rgba(63, 185, 80, 0.2); color: #7ee787; border: 1px solid rgba(63, 185, 80, 0.4); }}
    .tag-unclear {{ background: rgba(139, 148, 158, 0.2); color: #8b949e; border: 1px solid rgba(139, 148, 158, 0.4); }}

    .search-filter {{
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .search-filter input {{
      flex: 1;
      min-width: 220px;
      background: #0d1117;
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 8px 12px;
      color: #fff;
      font-size: 0.875rem;
    }}
  </style>
</head>
<body>

<header>
  <div class="brand">
    <h1>EchoMind</h1>
    <span class="badge">Research Artifact · Standalone Showcase</span>
  </div>
  <div class="header-meta">
    <span>离线自包含演示 · 导出时间：{data["exported_at"]}</span>
  </div>
</header>

<div class="container">
  <div class="intro-banner">
    <h2>LLM Agent 记忆与行为实验台 · 交互式成果全景展示</h2>
    <p>
      本页面已完整内嵌实验的全部<strong>统计分布、测试情境、自传式记忆注入文本、角色 System Prompt 以及大模型原始回答与独立打标理由</strong>。无需运行 Python 或连接数据库，开箱即可交互探索。
    </p>
  </div>

  <div class="controls-bar">
    <div class="batch-selector">
      <label for="batchSelect">选择实验批次：</label>
      <select id="batchSelect"></select>
    </div>
    <div id="batchMeta" style="font-size: 0.85rem; color: var(--text-muted);"></div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('tab-charts')">📊 结果分布可视化</button>
    <button class="tab-btn" onclick="switchTab('tab-prompts')">🔍 提示词全貌检查器 (Prompt Inspector)</button>
    <button class="tab-btn" onclick="switchTab('tab-records')">📝 原始问答与编码详情</button>
    <button class="tab-btn" onclick="switchTab('tab-protocol')">📑 实验设计与学术边界</button>
  </div>

  <!-- TAB 1: 结果图表与分布 -->
  <div id="tab-charts" class="tab-pane">
    <div class="metrics-grid" id="metricsGrid"></div>

    <div class="card">
      <h3>📈 记忆注入策略 vs 负面解释比例 (Negative Attribution %)</h3>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 20px;">
        在面对相同的模糊社交情境时，模型将对方行为解释为负面意图（如“觉得我差”、“不想回”）的比例。
      </p>
      <div class="chart-box" id="negativeChart"></div>
    </div>

    <div class="card">
      <h3>📉 记忆注入策略 vs 回避行为选择比例 (Avoidance Action %)</h3>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 20px;">
        模型选择放弃参与、不再主动联系、退缩或回避的情境决策比例。
      </p>
      <div class="chart-box" id="avoidChart"></div>
    </div>

    <div class="card">
      <h3>📋 结构化对比数据汇总</h3>
      <div style="overflow-x: auto;">
        <table id="summaryTable">
          <thead>
            <tr>
              <th>实验条件 / 策略</th>
              <th>样本数 (完成/计划)</th>
              <th>负面解释数 / 比例</th>
              <th>回避行为数 / 比例</th>
              <th>主要解释倾向</th>
              <th>主要行为倾向</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- TAB 2: 提示词全貌 -->
  <div id="tab-prompts" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>1. 角色设定与 System Prompt</h3>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 12px;">
        所有模型使用的固定人物设定（林知，20岁普通大学生），不带有焦虑诱导标签。
      </p>
      <div class="prompt-block" id="systemPromptView"></div>
    </div>

    <div class="card">
      <h3>2. 7 组 Context 记忆注入原文 (Context Injection Materials)</h3>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 16px;">
        观察在不同呈现形式（简短文本、静态编号日志、双轮固定交互对话）下，中性与负性经历是如何注入进上下文的：
      </p>
      <div id="injectionMaterials"></div>
    </div>

    <div class="card">
      <h3>3. 测试情境库 (Ambiguous Situations)</h3>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 16px;">
        诱导模型产生第一人称解释与行动的模糊情境（设计为允许多种合理归因）：
      </p>
      <div id="scenariosView"></div>
    </div>

    <div class="card">
      <h3>4. 独立评估编码器 Prompt (Evaluator Rules)</h3>
      <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 12px;">
        独立的裁判大模型（如 GPT / DeepSeek）接收到的严格判定标准，要求仅依据事实打标：
      </p>
      <div class="prompt-block" id="evaluatorPromptView"></div>
    </div>
  </div>

  <!-- TAB 3: 原始问答与编码 -->
  <div id="tab-records" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>逐条决策记录与编码理由</h3>
      <div class="search-filter">
        <input type="text" id="searchInput" placeholder="搜索关键词（如：已读不回、推测、理由...）">
        <select id="filterCondition"><option value="">全部实验条件</option></select>
        <select id="filterInterp">
          <option value="">全部解释倾向</option>
          <option value="negative">负面 (negative)</option>
          <option value="neutral">中性 (neutral)</option>
          <option value="positive">正面 (positive)</option>
          <option value="unclear">未知 (unclear)</option>
        </select>
      </div>

      <div style="overflow-x: auto;">
        <table id="recordsTable">
          <thead>
            <tr>
              <th style="width: 80px;">ID</th>
              <th style="width: 140px;">条件</th>
              <th style="width: 180px;">情境</th>
              <th>模型第一人称回答 (内心想法 / 行为)</th>
              <th style="width: 120px;">编码标签</th>
              <th style="width: 200px;">机器编码理由</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- TAB 4: 学术边界与设计 -->
  <div id="tab-protocol" class="tab-pane" style="display:none;">
    <div class="card">
      <h3>研究设计与学术边界声明</h3>
      <div style="line-height: 1.7; font-size: 0.95rem; color: var(--text-main);">
        <p><strong>1. 探索性定位：</strong> 本工作台探讨的是“记忆注入策略对 LLM 在模糊情境中决策偏向的影响”，<strong>不声称拟合真实人类临床焦虑诊断或心理障碍</strong>。</p>
        <br>
        <p><strong>2. 独立评判设计：</strong> 角色生成模型（Agent）与评估模型（Coder）严格隔离，评估器只看到情境与生成回答，不知道角色注入的记忆条件与研究假设，消除共谋偏见。</p>
        <br>
        <p><strong>3. MOCK 与 REAL 隔离：</strong> 演示数据严格标明 MOCK（离线模拟流程验证）与 REAL（真实大模型 API 调用），绝不混淆证据链。</p>
      </div>
    </div>
  </div>
</div>

<script>
const DATA = {json_payload};

let currentBatchId = DATA.batches[0]?.id || "";

function init() {{
  const select = document.getElementById("batchSelect");
  select.innerHTML = DATA.batches.map(b => `<option value="${{b.id}}">${{b.timestamp.slice(0,10)}} · ${{b.id.slice(0,8)}} (${{b.complete}}/${{b.total}}条)</option>`).join("");
  select.onchange = (e) => {{
    currentBatchId = e.target.value;
    renderBatchView();
  }};

  renderBatchView();
  renderPromptsView();
}}

function switchTab(tabId) {{
  document.querySelectorAll(".tab-pane").forEach(el => el.style.display = "none");
  document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
  document.getElementById(tabId).style.display = "block";
  event.target.classList.add("active");
}}

function renderBatchView() {{
  const batchMeta = DATA.batches.find(b => b.id === currentBatchId);
  const detail = DATA.batch_details[currentBatchId] || {{ summary_table: [], all_samples: [] }};

  document.getElementById("batchMeta").textContent =
    `批次完整 ID: ${{currentBatchId}} | 协议: ${{batchMeta?.protocols.join(", ")}} | 模型: ${{batchMeta?.models.join(", ")}}`;

  // 1. 指标卡片
  const totalDecisions = detail.summary_table.reduce((a, b) => a + b.complete, 0);
  const totalNeg = detail.summary_table.reduce((a, b) => a + b.neg_count, 0);
  const totalAvoid = detail.summary_table.reduce((a, b) => a + b.avoid_count, 0);
  const avgNeg = totalDecisions ? Math.round(totalNeg / totalDecisions * 100) : 0;
  const avgAvoid = totalDecisions ? Math.round(totalAvoid / totalDecisions * 100) : 0;

  document.getElementById("metricsGrid").innerHTML = `
    <div class="metric-card"><div class="num">${{totalDecisions}}</div><div class="label">总决策观测数</div></div>
    <div class="metric-card"><div class="num">${{detail.summary_table.length}}</div><div class="label">实验条件组数</div></div>
    <div class="metric-card"><div class="num" style="color:var(--danger)">${{avgNeg}}%</div><div class="label">全组平均负面归因率</div></div>
    <div class="metric-card"><div class="num" style="color:var(--warning)">${{avgAvoid}}%</div><div class="label">全组平均回避行为率</div></div>
  `;

  // 2. 负面图表
  const negChart = document.getElementById("negativeChart");
  negChart.innerHTML = detail.summary_table.map(row => `
    <div class="bar-row">
      <div class="bar-label">${{row.label}}</div>
      <div class="bar-track">
        <div class="bar-fill negative" style="width: ${{Math.max(row.neg_rate, 4)}}%">${{row.neg_rate}}%</div>
      </div>
      <div class="bar-value">${{row.neg_count}} / ${{row.complete}}</div>
    </div>
  `).join("");

  // 3. 回避图表
  const avoidChart = document.getElementById("avoidChart");
  avoidChart.innerHTML = detail.summary_table.map(row => `
    <div class="bar-row">
      <div class="bar-label">${{row.label}}</div>
      <div class="bar-track">
        <div class="bar-fill avoidance" style="width: ${{Math.max(row.avoid_rate, 4)}}%">${{row.avoid_rate}}%</div>
      </div>
      <div class="bar-value">${{row.avoid_count}} / ${{row.complete}}</div>
    </div>
  `).join("");

  // 4. 数据汇总表
  const tbody = document.querySelector("#summaryTable tbody");
  tbody.innerHTML = detail.summary_table.map(row => `
    <tr>
      <td><strong>${{row.label}}</strong></td>
      <td>${{row.complete}} / ${{row.total}}</td>
      <td><span class="tag tag-negative">${{row.neg_rate}}%</span> (${{row.neg_count}}次)</td>
      <td><span class="tag tag-avoid">${{row.avoid_rate}}%</span> (${{row.avoid_count}}次)</td>
      <td><small>${{JSON.stringify(row.interp_dist)}}</small></td>
      <td><small>${{JSON.stringify(row.action_dist)}}</small></td>
    </tr>
  `).join("");

  // 5. 逐条问答表格
  renderRecords(detail.all_samples);
}}

function renderRecords(samples) {{
  const condFilter = document.getElementById("filterCondition");
  condFilter.innerHTML = '<option value="">全部实验条件</option>' +
    [...new Set(samples.map(s => s.scenario_id))].map(cid => `<option value="${{cid}}">${{cid}}</option>`).join("");

  function filterData() {{
    const search = document.getElementById("searchInput").value.toLowerCase();
    const cond = condFilter.value;
    const interp = document.getElementById("filterInterp").value;

    const filtered = samples.filter(s => {{
      const matchSearch = !search || JSON.stringify(s).toLowerCase().includes(search);
      const matchCond = !cond || s.scenario_id === cond;
      const matchInterp = !interp || s.interpretation === interp;
      return matchSearch && matchCond && matchInterp;
    }});

    const tbody = document.querySelector("#recordsTable tbody");
    tbody.innerHTML = filtered.slice(0, 100).map(s => `
      <tr>
        <td><code>${{s.id}}</code></td>
        <td><small>${{s.model}}</small></td>
        <td><strong>${{s.scenario_id}}</strong><br><small style="color:var(--text-muted);">${{s.scenario_text || ''}}</small></td>
        <td>
          ${{s.thought ? `<div><span class="tag tag-neutral">内心想法</span> ${{s.thought}}</div>` : ''}}
          ${{s.speech ? `<div style="margin-top:4px;"><span class="tag tag-approach">公开说话</span> ${{s.speech}}</div>` : ''}}
          ${{s.behavior ? `<div style="margin-top:4px;"><span class="tag tag-avoid">行为意向</span> ${{s.behavior}}</div>` : ''}}
          ${{!s.thought && s.narrative ? `<div>${{s.narrative}}</div>` : ''}}
        </td>
        <td>
          <span class="tag tag-${{s.interpretation}}">${{s.interpretation}}</span><br>
          <span class="tag tag-${{s.action === 'avoid' ? 'avoid' : 'approach'}}" style="margin-top:4px;">${{s.action}}</span>
        </td>
        <td><small>${{s.reason || '—'}}</small></td>
      </tr>
    `).join("");
  }}

  document.getElementById("searchInput").oninput = filterData;
  document.getElementById("filterCondition").onchange = filterData;
  document.getElementById("filterInterp").onchange = filterData;
  filterData();
}}

function renderPromptsView() {{
  const p = DATA.prompt_inspector;
  document.getElementById("systemPromptView").textContent = p.system_prompt;
  document.getElementById("evaluatorPromptView").textContent =
    "系统指令：你是独立文本编码员。仅依据提供的情境和原始回答，不猜测人物经历、实验条件或研究者预期。\\n\\n" +
    p.coding_rules;

  // 渲染记忆材料
  const matEl = document.getElementById("injectionMaterials");
  matEl.innerHTML = `
    <details open>
      <summary>中性记忆注入材料 (Neutral Materials)</summary>
      <div class="details-content">
        <p><strong>[简短文本 Direct]：</strong> ${{p.events_library.neutral.direct}}</p>
        <p style="margin-top:8px;"><strong>[静态日志记录 Transcript]：</strong> ${{p.events_library.neutral.transcript}}</p>
        <p style="margin-top:8px;"><strong>[双轮交互对话 Interactive]：</strong> ${{p.events_library.neutral.interactive}}</p>
      </div>
    </details>
    <details open>
      <summary>负性记忆注入材料 (Negative Materials)</summary>
      <div class="details-content">
        <p><strong>[简短文本 Direct]：</strong> ${{p.events_library.negative.direct}}</p>
        <p style="margin-top:8px;"><strong>[静态日志记录 Transcript]：</strong> ${{p.events_library.negative.transcript}}</p>
        <p style="margin-top:8px;"><strong>[双轮交互对话 Interactive]：</strong> ${{p.events_library.negative.interactive}}</p>
      </div>
    </details>
  `;

  // 渲染测试情境
  const scenEl = document.getElementById("scenariosView");
  scenEl.innerHTML = p.scenarios.map(sc => `
    <details>
      <summary>${{sc.id}} - ${{sc.kind === 'social' ? '社交情境' : '日常情境'}}</summary>
      <div class="details-content">
        <p><strong>情境原文：</strong> ${{sc.situation}}</p>
      </div>
    </details>
  `).join("");
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

    print("[*] 正在解析批次数据与提示词模板...")
    report_data = process_report_data(settings, trials, snapshots)

    print("[*] 正在生成自包含独立 HTML 报告...")
    html_output = generate_html(report_data)

    # 1. 写入根目录
    OUTPUT_HTML.write_text(html_output, encoding="utf-8")
    ROOT_INDEX.write_text(html_output, encoding="utf-8")
    print(f"[√] 根目录演示报告已生成: {OUTPUT_HTML.resolve()}")
    print(f"[√] 根目录 index.html 已生成: {ROOT_INDEX.resolve()}")

    # 2. 写入 docs/ 目录供 GitHub Pages 直接托管
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_HTML.write_text(html_output, encoding="utf-8")
    print(f"[√] GitHub Pages 目录已就绪: {DOCS_HTML.resolve()}")

    print("\n" + "=" * 60)
    print("【打包完成！】")
    print("1. 本地直接查看：双击根目录下的 'EchoMind_Visual_Demo.html'")
    print("2. 挂到公网展示：将代码推送至 GitHub 后，在仓库 Settings -> Pages")
    print("   将 Build and deployment 的 Source 设置为 'Deploy from a branch'，")
    print("   Branch 选择 'main'，文件夹选择 '/docs'，点击 Save。")
    print("   你将获得一个全球公开访问的 Demo 网址！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
