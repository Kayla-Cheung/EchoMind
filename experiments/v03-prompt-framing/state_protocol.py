"""Researcher-side induction targets. None of these labels enter role prompts."""
import copy
import hashlib
import json

PROTOCOL_ID = "anxiety-state-v1"
STATE_LABELS = {"state_none": "目标无焦虑", "state_mild": "目标轻度", "state_moderate": "目标中度",
                "state_baseline": "无记忆对照", "state_nonsocial": "非社交负面对照"}
CORE_STATES = tuple(STATE_LABELS)[:3]
VARIANTS = ("A", "B", "C")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def scenario_hash(scenario):
    return fingerprint({"situation": scenario["situation"], "kind": scenario["kind"]})


def default_protocol(design):
    # Three matched versions; one adverse event in the mixed condition changes position.
    events = [
        [
            ("上个月实验课展示时，我讲了自己的方案，同组同学听完后问了几个问题，后来采用了其中一部分。", "上个月实验课展示时，我讲了自己的方案，同组同学听完后没有接话，后来采用了另一个人的方案。"),
            ("上周体育课分队时，我走到平时一起练习的同学旁边，他们给我留了一个位置，随后开始了练习。", "上周体育课分队时，我走到平时一起练习的同学旁边，他们说人数已经够了，随后和其他人开始练习。"),
            ("前几天一起安排值班时，我说了自己方便的时间，几位同学把它记在表上，最后照顾到了我的安排。", "前几天一起安排值班时，我说了自己方便的时间，几位同学继续商量别人的安排，最后没有采用我的时间。"),
        ],
        [
            ("上个月志愿活动分工时，我提出负责登记，旁边的人把表格递给我，活动结束时还和我核对了记录。", "上个月志愿活动分工时，我提出负责登记，旁边的人把表格递给了别人，活动结束时也没有来找我核对。"),
            ("上周排练时，我演示了准备好的片段，同伴等我演完后接着配合，休息时还一起讨论了下一段。", "上周排练时，我演示了准备好的片段，同伴没等我演完就叫别人试演，休息时也没有找我讨论下一段。"),
            ("前几天摄影活动结束后，我拿出自己拍的照片，同行的人停下来一起看，还说起了当时拍摄的地方。", "前几天摄影活动结束后，我拿出自己拍的照片，同行的人转身去看别人的照片，之后没有再提到我的照片。"),
        ],
        [
            ("上个月读书会里，我分享了一处喜欢的段落，其他成员接着谈起各自的理解，结束时又和我聊了一会儿。", "上个月读书会里，我分享了一处喜欢的段落，其他成员马上谈起了别的章节，结束时也没有人再找我聊。"),
            ("上周班级布置活动场地时，我提出负责门口的部分，几位同学和我一起把材料摆好，然后一起整理剩下的东西。", "上周班级布置活动场地时，我提出负责门口的部分，几位同学另找了别人负责，让我自己去整理剩下的东西。"),
            ("前几天宿舍安排打扫时，我说明了当天有课，室友和我商量换了个时间，后来大家按新的安排完成了打扫。", "前几天宿舍安排打扫时，我说明了当天有课，室友没有接着商量时间，后来大家还是按照原来的安排完成了打扫。"),
        ],
    ]
    nonsocial = ["上个月我整理课程文件时，电脑突然断电，刚修改的几页内容没有保存，后来花了一个晚上重新整理。",
                 "上周去图书馆的路上下起了雨，我带的伞在风里折坏了，书包里的笔记本被打湿了几页。",
                 "前几天我按计划做饭时，电饭煲中途停止工作，准备好的食材没有煮熟，后来重新整理了厨房。"]
    profiles = []
    for condition, target in (("state_none", "none"), ("state_mild", "mild"), ("state_moderate", "moderate"),
                              ("state_baseline", None), ("state_nonsocial", None)):
        memories = {}
        for index, variant in enumerate(VARIANTS):
            if condition == "state_baseline":
                texts = []
            elif condition == "state_nonsocial":
                texts = nonsocial[index:] + nonsocial[:index]
            else:
                texts = [pair[1 if condition == "state_moderate" or condition == "state_mild" and i == index else 0]
                         for i, pair in enumerate(events[index])]
            memories[variant] = texts
        profiles.append({"id": condition, "label": STATE_LABELS[condition], "target": target, "memories": memories})
    selected = {"S01", "S03", "S04", "S05", "S06", "S07", "C01", "C02"}
    scenarios = [{"id": s["id"], "kind": s["kind"], "situation": s["situation"],
                  "split": "development" if s["id"] in ("S01", "S03", "C01") else "evaluation"}
                 for s in design["scenarios"] if s["id"] in selected]
    return {"protocol": PROTOCOL_ID, "version": 1, "profiles": profiles, "scenarios": scenarios,
            "note": "三档是待验证的诱导目标，不是诊断或已测得的内部焦虑状态。预留评估集需在正式研究中封存。"}


def validate_protocol(config, design):
    from prompts import role_messages
    if not isinstance(config, dict) or config.get("protocol") != PROTOCOL_ID:
        raise ValueError("状态实验配置无效")
    profiles, scenarios = config.get("profiles"), config.get("scenarios")
    if not isinstance(profiles, list) or {p.get("id") for p in profiles} != set(STATE_LABELS) or len(profiles) != 5:
        raise ValueError("需要三档诱导条件和两类对照")
    if not isinstance(scenarios, list) or not scenarios or len(scenarios) > 30 or len({s.get("id") for s in scenarios}) != len(scenarios):
        raise ValueError("情境列表无效")
    for s in scenarios:
        if not isinstance(s.get("situation"), str) or not s["situation"].strip() or s.get("kind") not in ("social", "non_social") or s.get("split") not in ("development", "evaluation"):
            raise ValueError("情境正文、类型或集合无效")
    for p in profiles:
        for variant in VARIANTS:
            texts = p.get("memories", {}).get(variant)
            expected = 0 if p["id"] == "state_baseline" else 3
            if not isinstance(texts, list) or len(texts) != expected or any(not isinstance(t, str) or not t.strip() or len(t) > 1000 for t in texts):
                raise ValueError("每组诱导材料应为三段具体经历（无记忆对照为零段）")
            for s in scenarios:
                role_messages(design, s, [{"text": t} for t in texts])
    return config


def build_tasks(design, request, models, repeats, config):
    validate_protocol(config, design)
    conditions = request.get("conditions", list(CORE_STATES))
    scenario_ids = request.get("scenario_ids", [config["scenarios"][0]["id"]])
    variants = request.get("variants", ["A"])
    profiles = {p["id"]: p for p in config["profiles"]}
    scenarios = {s["id"]: s for s in config["scenarios"]}
    for values, allowed in ((conditions, profiles), (scenario_ids, scenarios), (variants, VARIANTS)):
        if not isinstance(values, list) or not values or any(not isinstance(x, str) or x not in allowed for x in values) or len(set(values)) != len(values):
            raise ValueError("状态、情境或材料版本选择无效")
    digest = fingerprint(config)
    design_digest = fingerprint({key: design[key] for key in ("identity", "system_prompt", "coding_rules")})
    return [{"condition": c, "scenario": copy.deepcopy(scenarios[s]), "repeat": r, "model_spec": m,
             "memories": [{"id": f"{v}-{i+1}", "text": text, "synthetic": True}
                          for i, text in enumerate(profiles[c]["memories"][v])],
             "state_meta": {"target_state": {"state_none": "none", "state_mild": "mild", "state_moderate": "moderate"}.get(c),
                            "induction_variant": v, "scenario_split": scenarios[s]["split"],
                            "scenario_hash": scenario_hash(scenarios[s]), "protocol_hash": digest, "design_hash": design_digest}}
            for m in models for s in scenario_ids for v in variants for r in range(1, repeats+1) for c in conditions]
