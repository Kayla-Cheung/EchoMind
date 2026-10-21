"""Provider adapters. Only final user-visible content enters behavioral coding."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from prompts import SCHEMA


def offline_mode():
    return os.getenv("SOS_OFFLINE") == "1"


class ProviderError(RuntimeError):
    def __init__(self, message, kind, http_status=None, attempts=1):
        super().__init__(message)
        self.meta = {"kind": kind, "http_status": http_status, "attempts": attempts}

PROVIDERS = {
    "deepseek": {"name": "DeepSeek", "model": "deepseek-flash", "base": "https://api.deepseek.com", "env": "DEEPSEEK_API_KEY", "api": "chat"},
    "minimax": {"name": "MiniMax", "model": "MiniMax-M3.1-Flash", "base": "https://api.minimax.io/v1", "env": "MINIMAX_API_KEY", "api": "chat"},
    "mimo": {"name": "Xiaomi MiMo", "model": "mimo-v2.6-flash", "base": "https://api.xiaomimimo.com/v1", "env": "MIMO_API_KEY", "api": "chat"},
    "gemini": {"name": "Google Gemini", "model": "gemini-3.8-flash", "base": "https://generativelanguage.googleapis.com/v1beta/openai", "env": "GEMINI_API_KEY", "api": "chat"},
    "openai": {"name": "OpenAI GPT", "model": "gpt-6-luna", "base": "https://api.openai.com/v1", "env": "OPENAI_API_KEY", "api": "responses"},
}
PRICING_URLS = {
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing",
    "minimax": "https://platform.minimax.io/docs/pricing/overview",
    "mimo": "https://mimo.mi.com/docs/en-US/pricing",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
    "openai": "https://developers.openai.com/api/docs/pricing",
}
MINIMAX_BASES = {"international": "https://api.minimax.io/v1", "china": "https://api.minimaxi.com/v1"}
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    region: str = "international"
    temperature: float | None = None
    reasoning_effort: str | None = None
    thinking: str | None = None

    def public(self):
        return {"provider": self.provider, "model": self.model, "region": self.region,
                "temperature": self.temperature, "reasoning_effort": self.reasoning_effort, "thinking": self.thinking}


def make_spec(value):
    if not isinstance(value, dict):
        raise ValueError("模型配置必须是对象")
    provider = value.get("provider")
    if provider not in PROVIDERS:
        raise ValueError("未知 Provider")
    model = value.get("model") or PROVIDERS[provider]["model"]
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model):
        raise ValueError("模型 ID 格式无效")
    region = value.get("region", "international")
    if provider == "minimax" and region not in MINIMAX_BASES:
        raise ValueError("MiniMax 区域只能为 international 或 china")
    if provider != "minimax" and region != "international":
        raise ValueError("该 Provider 不使用 MiniMax 区域")
    temp, effort, thinking = value.get("temperature"), value.get("reasoning_effort"), value.get("thinking")
    if temp is not None and (isinstance(temp, bool) or not isinstance(temp, (int, float)) or not 0 <= temp <= 2):
        raise ValueError("temperature 必须为 0–2")
    if provider == "minimax":
        if model == "MiniMax-M3.1-Flash":
            if thinking not in (None, "adaptive") or effort not in (None, "low", "medium", "high", "xhigh", "max"):
                raise ValueError("MiniMax-M3.1-Flash 始终推理，effort 仅支持 low/medium/high/xhigh/max")
        elif any(v is not None for v in (temp, effort, thinking)):
            raise ValueError("自定义 MiniMax 模型能力未知，请使用供应商默认参数")
    elif provider == "deepseek":
        if effort is not None or thinking not in (None, "enabled", "disabled"):
            raise ValueError("DeepSeek 此处仅支持 thinking enabled/disabled")
        if temp is not None and (model != "deepseek-flash" or thinking != "disabled"):
            raise ValueError("DeepSeek 温度仅在 deepseek-flash 非推理模式下可设置")
    elif provider == "mimo":
        if effort is not None or thinking not in (None, "enabled", "disabled"):
            raise ValueError("MiMo 此处仅支持 thinking enabled/disabled")
        if temp is not None and (model != "mimo-v2.6-flash" or thinking != "disabled"):
            raise ValueError("MiMo 温度仅在 mimo-v2.6-flash 非推理模式下可设置")
    elif provider == "gemini":
        if thinking is not None or effort not in (None, "low", "medium", "high"):
            raise ValueError("Gemini 3.8 Flash 仅支持 low/medium/high 推理等级")
        if temp is not None:
            raise ValueError("Gemini OpenAI 兼容接口的温度能力未在本适配器核实，请使用供应商默认参数")
        if model != "gemini-3.8-flash" and (temp is not None or effort is not None):
            raise ValueError("自定义 Gemini 模型能力未知，请使用供应商默认参数")
    else:
        if thinking is not None or effort not in (None, "none", "low", "medium", "high", "xhigh", "max"):
            raise ValueError("OpenAI 推理参数无效")
        if temp is not None and (model != "gpt-6-luna" or effort != "none"):
            raise ValueError("OpenAI 温度仅在 gpt-6-luna reasoning_effort=none 时可设置")
    return ModelSpec(provider, model, region, float(temp) if temp is not None else None, effort, thinking)


def provider_info():
    return [{"id": p, "name": d["name"], "default_model": d["model"], "base_url": d["base"],
             "configured": not offline_mode() and bool(os.getenv(d["env"], "").strip()), "env": d["env"],
             "pricing_url": PRICING_URLS[p]} for p, d in PROVIDERS.items()]


def endpoint(spec):
    d = PROVIDERS[spec.provider]
    base = MINIMAX_BASES[spec.region] if spec.provider == "minimax" else d["base"]
    return base.rstrip("/") + ("/responses" if d["api"] == "responses" else "/chat/completions")


def build_request(spec, messages, *, evaluator=False):
    if not isinstance(messages, list) or not messages:
        raise ValueError("消息不能为空")
    if spec.provider == "openai":
        body = {"model": spec.model, "input": messages, "store": False, "max_output_tokens": 1200 if evaluator else 1800}
        if spec.reasoning_effort is not None:
            body["reasoning"] = {"effort": spec.reasoning_effort}
        if evaluator:
            body["text"] = {"format": {"type": "json_schema", "name": "blind_coding", "strict": True, "schema": SCHEMA}}
    else:
        body = {"model": spec.model, "messages": messages, "stream": False,
                ("max_tokens" if spec.provider == "deepseek" else "max_completion_tokens"): 1200 if evaluator else 1800}
        if spec.provider in ("deepseek", "mimo") and spec.thinking:
            body["thinking"] = {"type": spec.thinking}
        if evaluator and spec.provider == "deepseek":
            body["response_format"] = {"type": "json_object"}
        if spec.provider == "minimax":
            body["reasoning_split"] = True
            if spec.thinking:
                body["thinking"] = {"type": spec.thinking}
        if spec.reasoning_effort is not None:
            body["reasoning_effort"] = spec.reasoning_effort
    if spec.temperature is not None:
        body["temperature"] = spec.temperature
    return body


def extract_final(spec, response):
    if spec.provider == "minimax" and (response.get("base_resp") or {}).get("status_code", 0) != 0:
        raise RuntimeError("MiniMax 返回非成功状态")
    if spec.provider == "openai":
        if response.get("status") not in (None, "completed"):
            raise RuntimeError(f"模型响应状态 {response.get('status')}")
        texts = [c.get("text", "") for item in response.get("output", []) if item.get("type") == "message"
                 for c in item.get("content", []) if c.get("type") == "output_text"]
    else:
        choice = (response.get("choices") or [{}])[0]
        if choice.get("finish_reason") in ("length", "content_filter"):
            raise RuntimeError(f"模型输出未完整结束: {choice.get('finish_reason')}")
        content = (choice.get("message") or {}).get("content")
        texts = [content] if isinstance(content, str) else [x.get("text", "") for x in content if x.get("type") == "text"] if isinstance(content, list) else []
    final = "\n".join(t for t in texts if isinstance(t, str)).strip()
    final = re.sub(r"<think>.*?</think>", "", final, flags=re.DOTALL | re.IGNORECASE).strip()
    if not final or final.startswith("<think>"):
        raise RuntimeError("模型未返回非空最终回答")
    return final


def call(spec, messages, *, evaluator=False, timeout=45, attempts=3, transport=None):
    if not 5 <= timeout <= 120 or not 1 <= attempts <= 5:
        raise ValueError("超时或重试参数无效")
    if offline_mode() and transport is None:
        raise ProviderError("离线模式禁止真实 API 调用", "offline")
    # Injected test transports never need to read real credentials.
    key = "" if transport is not None else os.getenv(PROVIDERS[spec.provider]["env"], "").strip()
    if not key and transport is None:
        raise ProviderError(f"{PROVIDERS[spec.provider]['env']} 未配置", "authentication")
    body, url = build_request(spec, messages, evaluator=evaluator), endpoint(spec)
    last = None
    total_began = time.monotonic()
    for index in range(attempts):
        try:
            if transport is not None:
                data = transport(url, body, timeout)
            else:
                req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as res:
                    data = json.load(res)
            final = extract_final(spec, data)
            return final, {"response_id": data.get("id"), "usage": data.get("usage") or {},
                "response_model": data.get("model"), "latency_ms": round((time.monotonic() - total_began) * 1000),
                "attempts": index + 1, "sent_parameters": {k: v for k, v in body.items() if k not in ("input", "messages")},
                "endpoint": url}
        except urllib.error.HTTPError as exc:
            # Provider error bodies can echo credentials or request contents.
            # Keep structured HTTP diagnostics without persisting those bodies.
            kind = "authentication" if exc.code in (401, 403) else "rate_limit" if exc.code == 429 else "http"
            last = ProviderError(f"{spec.provider} HTTP {exc.code}", kind, exc.code, index + 1)
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            last = ProviderError(f"{spec.provider} 连接或超时失败", "transport", attempts=index + 1)
        except Exception as exc:
            detail = str(exc).replace(key, "[REDACTED]") if key else str(exc)
            last = ProviderError(detail[:350], "response", attempts=index + 1)
            break
        if index + 1 < attempts:
            time.sleep(min(2 ** index, 4))
    raise last
