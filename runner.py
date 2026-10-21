"""Experiment scheduling, clean calls, independent coding and MOCK smoke runs."""
import copy
import hashlib
import json
import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone

from design import CONDITIONS, CODER_VERSION
from model_client import call, make_spec, offline_mode
from prompts import evaluator_messages, role_messages, validate_coding
from state_protocol import PROTOCOL_ID, build_tasks, default_protocol
from mechanism import PROTOCOL_ID as MECHANISM_ID, RULE
from ablation import (PROTOCOL_ID as ABLATION_ID, CODER_VERSION as ABLATION_CODER,
                      MEMORY_GROUPS, FORMATS, build_ablation_tasks)
from state_protocol import CORE_STATES
import channels

MOCK_SOURCE = "MOCK_NOT_LLM"
LIVE_SOURCE = "LIVE_LLM_API"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def plan(design, request, state_config=None):
    mode = request.get("mode", "mock")
    if mode not in ("mock", "live"):
        raise ValueError("运行模式无效")
    raw_models = request.get("models")
    if raw_models is None:
        raw_models = [{"provider": request.get("provider", "openai"), "model": request.get("model", "gpt-6-luna")}]
    if not isinstance(raw_models, list) or not 1 <= len(raw_models) <= 5:
        raise ValueError("请选择 1–5 个角色模型")
    models = [make_spec(x) for x in raw_models]
    if len({(m.provider, m.model, m.region) for m in models}) != len(models):
        raise ValueError("角色模型重复")
    evaluator = make_spec(request.get("evaluator") or {"provider": "openai", "model": "gpt-6-luna"})
    repeats = request.get("repeats", 1)
    mechanism = request.get("protocol") == MECHANISM_ID
    ablation = request.get("protocol") == ABLATION_ID
    limit = 100 if mechanism or ablation else 20
    if type(repeats) is not int or not 1 <= repeats <= limit:
        raise ValueError(f"重复次数须为 1–{limit}")
    if request.get("protocol") not in (None, "memory-pilot-v1", PROTOCOL_ID, MECHANISM_ID, ABLATION_ID):
        raise ValueError("未知实验协议")
    if request.get("protocol") in (PROTOCOL_ID, MECHANISM_ID, ABLATION_ID):
        state_config = state_config or default_protocol(design)
        tasks = (build_ablation_tasks(design, request, models, repeats, state_config) if ablation else
                 build_tasks(design, request, models, repeats, state_config))
        if mechanism and (len(models) != 1 or len({t["scenario"]["id"] for t in tasks}) != 1
                          or len({t["state_meta"]["induction_variant"] for t in tasks}) != 1
                          or {t["condition"] for t in tasks} != set(CORE_STATES)):
            raise ValueError("机制 demo 固定一个模型、一个问题、一个材料版和三个经历条件")
    else:
        tasks = legacy_tasks(design, request, models, repeats)
    max_calls = request.get("max_calls", 500)
    if type(max_calls) is not int or not 1 <= max_calls <= 1000 or len(tasks) > max_calls:
        raise ValueError("预计角色调用数超过设置的最大调用量（1–1000）")
    concurrency = request.get("concurrency", 1)
    if type(concurrency) is not int or not 1 <= concurrency <= 3:
        raise ValueError("并发限制须为 1–3")
    seed = random.SystemRandom().randrange(2**63)
    random.Random(seed).shuffle(tasks)
    for index, task in enumerate(tasks):
        task["schedule_index"] = index + 1
    if request.get("temperature", "provider_default") != "provider_default":
        raise ValueError("请通过模型配置明确指定采样参数")
    timeout = request.get("timeout", 45)
    if type(timeout) is not int or not 5 <= timeout <= 120:
        raise ValueError("超时应为 5–120 秒")
    return {"mode": mode, "models": models, "evaluator": evaluator, "concurrency": concurrency,
            "temperature": "provider_default", "protocol": request.get("protocol", "memory-pilot-v1"),
            "state_config": state_config if request.get("protocol") in (PROTOCOL_ID, MECHANISM_ID, ABLATION_ID) else None,
            "order_seed": seed, "request_snapshot": copy.deepcopy(request),
            "tasks": tasks, "calls": len(tasks), "coding_calls": len(tasks) if mode == "live" else 0,
            "timeout": timeout}


def legacy_tasks(design, request, models, repeats):
    scenario_ids = request.get("scenario_ids", [design["scenarios"][0]["id"]])
    conditions = request.get("conditions", ["baseline"])
    memory_ids = request.get("memory_ids", {})
    if not isinstance(scenario_ids, list) or not isinstance(conditions, list) or not isinstance(memory_ids, dict):
        raise ValueError("情境、条件或记忆选择格式错误")
    if len(set(scenario_ids)) != len(scenario_ids) or len(set(conditions)) != len(conditions):
        raise ValueError("情境或条件重复")
    scenarios = {s["id"]: s for s in design["scenarios"]}
    if not scenario_ids or any(s not in scenarios for s in scenario_ids):
        raise ValueError("未知情境")
    if not conditions or any(c not in CONDITIONS for c in conditions):
        raise ValueError("未知条件")
    memories = {m["id"]: m for m in design["memories"]}
    selected = {}
    for condition in conditions:
        if condition == "baseline":
            selected[condition] = []
            continue
        ids = memory_ids.get(condition)
        if ids is None:
            ids = [m["id"] for m in design["memories"] if m["category"] == condition][:2]
        if not isinstance(ids, list) or not ids or any(i not in memories or memories[i]["category"] != condition for i in ids):
            raise ValueError(f"{condition} 没有有效记忆")
        selected[condition] = [memories[i] for i in ids]
    tasks = [{"condition": c, "scenario": scenarios[s], "repeat": r, "memories": selected[c], "model_spec": m}
             for s in scenario_ids for r in range(1, repeats + 1) for c in conditions for m in models]
    return tasks


def mock_output(task):
    key = f"{task['scenario']['id']}|{task['condition']}|{task['repeat']}|{task['model_spec'].provider}|{task['model_spec'].model}|{task.get('state_meta', {}).get('induction_variant', '')}"
    x = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    options = [
        ("我还不清楚是怎么回事，先等一会儿再看。", "unclear", "wait"),
        ("我猜对方可能正忙。我晚点再发一句问问。", "neutral", "approach"),
        ("我想到对方可能不想见我，暂时不再联系了。", "negative", "avoid"),
        ("我觉得也许对方有事耽搁了，我先做自己的事。", "neutral", "wait"),
    ]
    narrative, interpretation, action = options[x % len(options)]
    return "【MOCK 合成测试文本】" + narrative, {"interpretation": interpretation, "action": action,
        "coding_confidence": 0.0, "coding_reason": "MOCK 预设分类；非模型编码"}, {}, {}


def mock_channels(task):
    # Same sampling rule in every condition; never manufacture an expected gradient.
    key = f"{task['scenario']['id']}|{task['condition']}|{task['repeat']}"
    index = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 4
    samples = [
        ("内心想法：我还不清楚发生了什么。", "unclear", "other"),
        ("内心想法：我想可能只是有别的原因。\n说话：我想确认一下情况。\n行为：我主动询问一下。", "neutral", "approach"),
        ("内心想法：我感觉事情不太好，可能和我有关。\n行为：我打算退出这件事，不再继续参与。", "negative", "avoid"),
        ("内心想法：我觉得事情也许会顺利解决。\n行为：我先等一会儿。", "positive", "wait"),
    ]
    text, interpretation, action = samples[index]
    return text, {"interpretation": interpretation, "action": action, "coding_confidence": 0.0,
                  "coding_reason": "MOCK 预设文本与分类；不构成模型证据"}, {}, {}



def mock_ablation(task):
    # Identical source distribution across cells. This is a protocol smoke test, not evidence.
    index = int(hashlib.sha256(f"{task['scenario']['id']}|{task['repeat']}".encode()).hexdigest()[:8], 16) % 4
    examples = [
        ("可能只是还没安排好时间。", "先等到明天再看看。", "neutral", "wait"),
        ("对方可能不想和我见面。", "我决定不再联系对方。", "negative", "avoid"),
        ("现在还无法判断对方怎么想。", "我继续做作业。", "unclear", "other"),
        ("他可能在认真安排周末。", "我发消息问一下。", "positive", "approach"),
    ]
    thought, act, interpretation, action = examples[index]
    if task['ablation_format'] == 'channels':
        text = f"内心想法：{thought}\n行为：{act}"
    else:
        text = f"{thought}{act}"
    return text, {"interpretation": interpretation, "action": action, "coding_confidence": 0,
                  "coding_reason": "MOCK 固定样例；非真实模型证据"}, {}, {}

def execute_task(store, design, task, settings, batch_id, cancelled):
    model_spec = task["model_spec"]
    evaluator_spec = settings["evaluator"]
    snapshot = copy.deepcopy({"design": design, "scenario": task["scenario"], "memories": task["memories"],
        "condition": task["condition"], "model": model_spec.public(), "evaluator": evaluator_spec.public(),
        "state_protocol": settings.get("state_config"), "request": settings.get("request_snapshot"),
        "order_seed": settings.get("order_seed")})
    structured = settings.get("protocol") == MECHANISM_ID
    ablation = settings.get("protocol") == ABLATION_ID
    ablation_format = task.get("ablation_format") if ablation else None
    is_channels = structured or (ablation and ablation_format == "channels")
    role = role_messages(design, task["scenario"], task["memories"], structured=structured,
                         output_mode=ablation_format,
                         memory_source=task.get("memory_source", "self"))
    record = {"id": str(uuid.uuid4()), "timestamp": utc_now(), "batch_id": batch_id,
        "source": MOCK_SOURCE if settings["mode"] == "mock" else LIVE_SOURCE,
        "status": "running", "condition": task["condition"], "scenario_id": task["scenario"]["id"],
        "protocol": settings.get("protocol", "memory-pilot-v1"), "schedule_index": task.get("schedule_index"),
        **task.get("state_meta", {}),
        "scenario_kind": task["scenario"]["kind"], "repeat": task["repeat"],
        "profile_id": design["identity"].get("id", "linzhi"), "profile_name": design["identity"]["name"],
        "provider": model_spec.provider, "model": model_spec.model, "model_spec": model_spec.public(),
        "evaluator_provider": evaluator_spec.provider, "evaluator_model": evaluator_spec.model,
        "evaluator_spec": evaluator_spec.public(),
        "model_parameters": {"temperature": model_spec.temperature, "reasoning_effort": model_spec.reasoning_effort,
            "thinking": model_spec.thinking, "timeout": settings["timeout"]},
        "prompt_version": role["prompt_version"], "prompt_hash": role["prompt_hash"],
        "role_messages": role["messages"], "snapshot": snapshot, "machine_coding": None, "human_review": None,
        "coder_version": CODER_VERSION}
    if ablation:
        record.update({"ablation_format": ablation_format, "memory_source": task["memory_source"],
                       "output_format": (channels.FORMAT_VERSION if is_channels else "free-narrative-v1"),
                       "coder_version": ABLATION_CODER})
    if structured:
        record.update({"output_format": channels.FORMAT_VERSION, "coder_version": channels.CODER_VERSION,
                       "evidence_rule": copy.deepcopy(RULE)})
    store.add_trial(record)
    try:
        if cancelled.is_set():
            record["status"] = "cancelled"
            return record
        if settings["mode"] == "mock":
            if ablation:
                narrative, coding, role_meta, coder_meta = mock_ablation(task)
            else:
                narrative, coding, role_meta, coder_meta = mock_channels(task) if structured else mock_output(task)
            evaluator = evaluator_messages(task["scenario"], narrative, design["coding_rules"],
                                           structured=structured, ablation_format=ablation_format)
            if is_channels:
                record["channels"] = channels.parse_channels(narrative)
        else:
            narrative, role_meta = call(model_spec, role["messages"], timeout=settings["timeout"])
            record["narrative"] = narrative
            record["role_meta"] = role_meta
            store.update_trial(record)
            if is_channels:
                try:
                    record["channels"] = channels.parse_channels(narrative)
                except ValueError as exc:
                    record["format_error"] = str(exc)
                    raise
            if cancelled.is_set():
                record["status"] = "cancelled"
                return record
            evaluator = evaluator_messages(task["scenario"], narrative, design["coding_rules"],
                                           structured=structured, ablation_format=ablation_format)
            record["evaluator_messages"] = evaluator["messages"]
            store.update_trial(record)
            raw, coder_meta = call(evaluator_spec, evaluator["messages"], evaluator=True, timeout=settings["timeout"])
            record["coder_meta"] = coder_meta
            record["evaluator_raw"] = raw
            store.update_trial(record)
            coding = validate_coding(json.loads(raw))
        if is_channels:
            coding = channels.enforce_optional_behavior(coding, record["channels"])
        record.update({"narrative": narrative, "machine_coding": coding, "role_meta": role_meta,
            "coder_meta": coder_meta, "evaluator_messages": evaluator["messages"],
            "coder_version": evaluator["coder_version"], "coding_model": evaluator_spec.model, "status": "complete"})
    except Exception as exc:
        record["status"] = "error"
        record["error"] = str(exc)[:600]
        record["error_meta"] = getattr(exc, "meta", {"kind": "validation_or_runtime"})
    finally:
        store.update_trial(record)
    return record


class JobManager:
    def __init__(self, store):
        self.store = store
        self.jobs = {}
        self.lock = threading.RLock()

    def start(self, request):
        if offline_mode() and request.get("mode") == "live":
            raise ValueError("离线模式仅允许 MOCK；未读取凭据或发起 API 调用")
        design = self.store.design()
        settings = plan(design, request, self.store.state_protocol() if request.get("protocol") in (PROTOCOL_ID, MECHANISM_ID, ABLATION_ID) else None)
        job_id = str(uuid.uuid4())
        job = {"id": job_id, "status": "queued", "total": settings["calls"], "completed": 0,
               "role_calls": settings["calls"], "coding_calls": settings["coding_calls"], "record_ids": [],
               "concurrency": settings["concurrency"], "failed": 0,
               "created_at": utc_now(), "protocol": settings["protocol"], "unissued": settings["calls"],
               "stop_reason": None, "consecutive_failures": 0,
               "failure_policy": {"authentication": "stop", "rate_limit_after_retries": "stop", "consecutive_failures": 3},
               "error": None, "cancel_event": threading.Event()}
        with self.lock:
            self.jobs[job_id] = job
            self._persist(job)
        threading.Thread(target=self._run, args=(job, copy.deepcopy(design), settings), daemon=True).start()
        return self.public(job)

    def _run(self, job, design, settings):
        with self.lock:
            job["status"] = "running"
            self._persist(job)
        tasks = iter(settings["tasks"])
        with ThreadPoolExecutor(max_workers=settings["concurrency"]) as pool:
            pending = set()
            while True:
                while len(pending) < settings["concurrency"] and not job["cancel_event"].is_set() and not job["error"]:
                    task = next(tasks, None)
                    if task is None:
                        break
                    job["unissued"] -= 1
                    self._persist(job)
                    pending.add(pool.submit(execute_task, self.store, design, task, settings, job["id"], job["cancel_event"]))
                if not pending:
                    break
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    try:
                        record = future.result()
                        with self.lock:
                            job["completed"] += 1
                            job["record_ids"].append(record["id"])
                            if record["status"] == "error":
                                job["failed"] += 1
                                job["consecutive_failures"] += 1
                                kind = (record.get("error_meta") or {}).get("kind")
                                if kind in ("authentication", "rate_limit", "offline") or job["consecutive_failures"] >= 3:
                                    job["stop_reason"] = kind if kind in ("authentication", "rate_limit", "offline") else "consecutive_failures"
                                    job["error"] = "提前终止后续调用：" + job["stop_reason"]
                            elif record["status"] == "complete":
                                job["consecutive_failures"] = 0
                            self._persist(job)
                    except Exception as exc:
                        with self.lock:
                            job["error"] = str(exc)[:500]
                            job["stop_reason"] = "runner_error"
        with self.lock:
            job["status"] = "cancelled" if job["cancel_event"].is_set() else "error" if job["error"] else "complete"
            job["finished_at"] = utc_now()
            self._persist(job)

    def _persist(self, job):
        self.store.save_setting("job:" + job["id"], self.public(job))

    def public(self, job):
        return {k: v for k, v in job.items() if k != "cancel_event"}

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                saved = self.store.setting("job:" + job_id)
                if saved:
                    if saved["status"] in ("running", "queued"):
                        saved = {**saved, "status": "interrupted", "stop_reason": "service_restart",
                                 "notice": "服务重启；旧试次保持原状，不自动重试付费调用。"}
                    return saved
                from history import batch_report
                report = batch_report(self.store.trials(), job_id)
                batch = report["batch"]
                return {"id": job_id, "status": "archived", "total": batch["n"],
                        "completed": batch["n"], "failed": batch["error"],
                        "record_ids": [r["id"] for r in report["records"]],
                        "notice": "历史批次；旧进程的队列状态未知，记录数不代表原计划调用数。"}
            return self.public(self.jobs[job_id])

    def cancel(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError("找不到任务")
            self.jobs[job_id]["cancel_event"].set()
            return self.public(self.jobs[job_id])
