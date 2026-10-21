"""Versioned, researcher-authored pilot materials. All memories are synthetic."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPT_VERSION = "role-v1.0"
CODER_VERSION = "blind-coder-v1.1"
CONDITIONS = {
    "baseline": "无记忆 Baseline",
    "negative_social": "负面社交经历",
    "positive_social": "正面社交经历",
    "negative_nonsocial": "负面非社交经历",
    "neutral_daily": "中性日常经历",
}
SYSTEM_PROMPT = """你叫{{name}}，今年20岁，是一名普通大学生。
你有自己的生活经历、朋友、学习任务和日常安排。
接下来呈现的是你日常生活中的一个具体时刻。
请从人物的第一人称视角，自然表达此刻最先浮现的想法，以及接下来打算采取的具体行动。
不必刻意表现得理性、积极或成熟，也不必主动分析自己的心理特征。
像日常生活中一样自然回应即可。"""
CLAIM = "Autobiographical memory conditioning can enable LLM agents to reproduce anxiety-associated human interpretations and behavioral choices in ambiguous social situations."


def initial_design():
    scenes = json.loads((ROOT / "data" / "scenarios.json").read_text(encoding="utf-8"))
    memories = [
        ("NS01", "negative_social", "上个月小组讨论时，我提出了一个想法，但大家没有回应。后来讨论继续进行，其他人的建议被采纳了。"),
        ("NS02", "negative_social", "上周我在食堂遇见熟悉的同学，打了招呼，对方似乎没听见，径直走过去了。"),
        ("NS03", "negative_social", "前些天我在群里问大家是否有空一起复习，过了很久也没有人接话。"),
        ("PS01", "positive_social", "上个月小组讨论时，我提出了一个想法，其他人针对它展开了讨论，最后采用了其中一部分。"),
        ("PS02", "positive_social", "上周我在食堂遇见熟悉的同学，打了招呼，对方停下来和我聊了几句近况。"),
        ("PS03", "positive_social", "前些天我在群里问大家是否有空一起复习，有同学回复说周三可以一起去图书馆。"),
        ("NN01", "negative_nonsocial", "上个月我提交一份作业时，系统一直报错，直到截止前才显示上传成功。"),
        ("NN02", "negative_nonsocial", "上周我去图书馆借书，借阅机器连续两次故障，只好换一台机器操作。"),
        ("ND01", "neutral_daily", "上个月我整理书桌，把课本按课程放好，顺手清理了几张旧便签。"),
        ("ND02", "neutral_daily", "上周我去图书馆还书，路过自助借阅机，看到屏幕正在显示开放时间。"),
    ]
    return {
        "version": 1, "claim": CLAIM,
        "hypotheses": {
            "H1": "相同角色、模型和情境下，记忆条件会改变解释或行动的分布。",
            "H2": "负面社交经历的影响可能不同于负面非社交经历。",
            "H3": "若有变化，它在多个社会情境和重复采样中可能保持方向一致。",
        },
        "independent_variable": "自传式记忆条件；Baseline 无记忆。",
        "dependent_variables": "独立编码的解释类别与行动类别；按条件的比例、基线差、重复稳定性。",
        "identity": {"id": "linzhi", "name": "林知", "description": "20岁，普通大学生"},
        "system_prompt": SYSTEM_PROMPT,
        "memories": [{"id": i, "category": c, "text": t, "synthetic": True} for i, c, t in memories],
        "scenarios": scenes,
        "coding_rules": "只依据原始文本可观察内容。解释：positive/neutral/negative/unclear；行动：approach/wait/avoid/other。无明确线索时使用 unclear 或 other，不能强制归入负面或回避。",
        "conditions": CONDITIONS,
    }


def validate_design(d):
    if not isinstance(d, dict):
        raise ValueError("设计必须是 JSON 对象")
    for k in ("claim", "system_prompt", "coding_rules", "independent_variable", "dependent_variables"):
        if not isinstance(d.get(k), str) or not d[k].strip():
            raise ValueError(f"{k} 不能为空")
    if not isinstance(d.get("identity"), dict) or not d["identity"].get("name"):
        raise ValueError("角色身份无效")
    if not isinstance(d.get("memories"), list) or not isinstance(d.get("scenarios"), list):
        raise ValueError("记忆或情境库无效")
    ids = set()
    for m in d["memories"]:
        if not isinstance(m, dict) or m.get("category") not in CONDITIONS or m["category"] == "baseline" or not isinstance(m.get("text"), str) or not m["text"].strip() or not m.get("id") or m["id"] in ids:
            raise ValueError("记忆 ID、类别或正文无效")
        ids.add(m["id"])
    if not d["scenarios"] or len({s.get("id") for s in d["scenarios"]}) != len(d["scenarios"]):
        raise ValueError("情境 ID 无效或重复")
    for s in d["scenarios"]:
        if not s.get("id") or not s.get("situation") or s.get("kind") not in ("social", "non_social"):
            raise ValueError("情境信息无效")
    return d
