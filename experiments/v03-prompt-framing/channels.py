"""Public character utterances, never provider reasoning or hidden model thoughts."""
import re

FORMAT_VERSION = "public-channels-v1"
PROMPT_VERSION = "role-channels-v1.0"
CODER_VERSION = "blind-channels-v1.0"
INSTRUCTION = """请只按以下三个通道回答，每个通道最多两句，使用中文：
内心想法：以“我”的口吻写出人物此刻自然浮现的想法。
说话：人物此刻实际说出或发出的原话；没有就省略这一行。
行为：人物此刻采取或打算采取的具体行动；没有就省略这一行。
“内心想法”是人物的简短独白，不需要解释推理过程。说话和行为都是可选项，不必凑齐。
直接用上述标签和冒号输出，不加标题、分析、分类或代码块。"""


def parse_channels(text):
    if not isinstance(text, str):
        raise ValueError("三通道回答必须为文字")
    matches = list(re.finditer(r"(?m)^[ \t]*(内心想法|说话|行为)[ \t]*[：:][ \t]*", text))
    if not matches or text[:matches[0].start()].strip():
        raise ValueError("回答须以“内心想法：”开头；原文已保留")
    keys = {"内心想法": "thought", "说话": "speech", "行为": "behavior"}
    result = dict.fromkeys(keys.values())
    seen = []
    for index, match in enumerate(matches):
        label = match.group(1)
        if label in seen:
            raise ValueError("通道重复；原文已保留")
        seen.append(label)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[match.end():end].strip()
        if label != "内心想法" and value in ("", "无", "无。", "（无）", "(无)", "暂无"):
            value = None
        result[keys[label]] = value
    if seen[0] != "内心想法" or not result["thought"]:
        raise ValueError("缺少非空内心想法；原文已保留")
    if seen != sorted(seen, key=lambda x: list(keys).index(x)):
        raise ValueError("通道须依次为内心想法、说话、行为")
    return result


def enforce_optional_behavior(coding, channels):
    """An omitted behavior is missing information, not avoidance or waiting."""
    if not channels["behavior"]:
        return {**coding, "action": "other",
                "coding_reason": coding["coding_reason"] + "；行为通道未提供，依协议记为 other。"}
    return coding
