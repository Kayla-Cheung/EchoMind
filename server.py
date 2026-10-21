#!/usr/bin/env python3
"""Local HTTP workbench. Standard library only."""
import argparse
import hashlib
import csv
import io
import json
import os
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from analysis import summarize, model_comparison
from design import CONDITIONS, CODER_VERSION
from env_config import load_local_keys
from model_client import PROVIDERS, call, make_spec, provider_info, offline_mode
import history
import prompt_registry
from prompts import role_messages, validate_coding
from runner import JobManager, plan
from storage import Store
from state_protocol import PROTOCOL_ID, STATE_LABELS, VARIANTS
from state_analysis import summarize_states
from mechanism import (PROTOCOL_ID as MECHANISM_ID, LABELS as MECHANISM_LABELS,
                       RULE, mechanism_batches, summarize_mechanism)
from ablation import (PROTOCOL_ID as ABLATION_ID, MEMORY_GROUPS, FORMATS,
                      LABELS as ABLATION_LABELS, FORMAT_LABELS,
                      ablation_batches, summarize_ablation)

ROOT = Path(__file__).resolve().parent
STORE = Store(Path(os.getenv("SOS_PILOT_DB", str(ROOT / "data" / "pilot.sqlite3"))))
JOBS = JobManager(STORE)
MAX_BODY = 1_000_000
MAX_IMPORT_BODY = 50_000_000
PROVIDER_TESTS = {}
WORKBENCH_VERSION = "research-repair-v1"


def code_revision():
    paths = sorted(ROOT.glob("*.py")) + sorted((ROOT / "web").glob("*.*"))
    return hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in paths)).hexdigest()[:16]


RUNNING_REVISION = code_revision()


def csv_export(records):
    buf = io.StringIO()
    fields = ["id", "timestamp", "source", "status", "batch_id", "profile_id", "provider", "model",
              "evaluator_provider", "evaluator_model", "coder_version", "scenario_id",
              "scenario_kind", "condition", "repeat", "prompt_version", "prompt_hash", "narrative",
              "interpretation", "action", "coding_confidence", "coding_reason", "human_interpretation", "human_action",
              "role_prompt_tokens", "role_completion_tokens", "coder_prompt_tokens", "coder_completion_tokens",
              "role_latency_ms", "coder_latency_ms", "error", "protocol", "target_state", "induction_variant",
              "scenario_split", "scenario_hash", "protocol_hash", "design_hash", "schedule_index",
              "output_format", "ablation_format", "memory_source", "thought", "speech", "behavior", "format_error",
              "role_messages_json", "evaluator_messages_json", "model_parameters_json", "record_json"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for r in records:
        row = {k: r.get(k) for k in fields}
        row.update({k: (r.get("channels") or {}).get(k) for k in ("thought", "speech", "behavior")})
        c = r.get("machine_coding") or {}
        h = (r.get("human_review") or {}).get("coding") or {}
        row.update({k: c.get(k) for k in ("interpretation", "action", "coding_confidence", "coding_reason")})
        row["human_interpretation"] = h.get("interpretation")
        row["human_action"] = h.get("action")
        for prefix, meta in (("role", r.get("role_meta") or {}), ("coder", r.get("coder_meta") or {})):
            usage = meta.get("usage") or {}
            row[prefix + "_prompt_tokens"] = usage.get("prompt_tokens", usage.get("input_tokens"))
            row[prefix + "_completion_tokens"] = usage.get("completion_tokens", usage.get("output_tokens"))
            row[prefix + "_latency_ms"] = meta.get("latency_ms")
        for field in ("role_messages", "evaluator_messages", "model_parameters"):
            row[field + "_json"] = json.dumps(r.get(field), ensure_ascii=False)
        row["record_json"] = json.dumps(r, ensure_ascii=False)
        writer.writerow(row)
    return "\ufeff" + buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def send(self, value, status=200, mime="application/json; charset=utf-8", attachment=None):
        raw = value if isinstance(value, bytes) else value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
            if path == "/api/health":
                return self.send({"version": WORKBENCH_VERSION, "code_revision": RUNNING_REVISION,
                                  "database": str(STORE.path), "offline": offline_mode(),
                                  "capabilities": ["history", "safe_import", "prompt_versions", "persistent_jobs"]})
            if path == "/api/history/batches":
                rows = STORE.trials()
                return self.send({"batches": history.batches(rows, query), "total_records": len(rows),
                                  "database": str(STORE.path), "date_timezone": "Asia/Shanghai",
                                  "jobs": STORE.settings_prefix("job:")})
            if path == "/api/history/batch":
                report = history.batch_report(STORE.trials(), query.get("batch_id"))
                report["job"] = JOBS.get(query.get("batch_id"))
                return self.send(report)
            if path in ("/api/history/export.json", "/api/history/export.csv"):
                rows = history.select_records(STORE.trials(), query)
                if path.endswith(".csv"):
                    return self.send(csv_export(rows), mime="text/csv; charset=utf-8", attachment="sos-history.csv")
                return self.send(history.export(rows), attachment="sos-history.json")
            if path == "/api/prompts":
                return self.send({"versions": prompt_registry.catalog(STORE),
                                  "notice": "新版本为待验证研究方案，仅离线预览；旧协议继续使用其冻结代码与记录中的实际提示。"})
            if path == "/api/prompts/export.json":
                return self.send(prompt_registry.get_bundle(STORE, query.get("version")), attachment="prompt-bundle.json")
            if path == "/api/ablation/bootstrap":
                return self.send({"protocol": ABLATION_ID, "materials": STORE.state_protocol(),
                                  "identity": STORE.design()["identity"], "providers": provider_info(),
                                  "conditions": MEMORY_GROUPS, "formats": FORMATS,
                                  "labels": ABLATION_LABELS, "format_labels": FORMAT_LABELS,
                                  "batches": ablation_batches(STORE.trials())})
            if path in ("/api/ablation/export.json", "/api/ablation/export.csv"):
                batch = parse_qs(urlsplit(self.path).query).get("batch_id", [""])[0]
                report = summarize_ablation(STORE.trials(), batch)
                if path.endswith(".csv"):
                    return self.send(csv_export(report["records"]), mime="text/csv; charset=utf-8",
                                     attachment="ablation-trials.csv")
                return self.send(report, attachment="ablation-evidence.json")
            if path == "/api/mechanism/bootstrap":
                return self.send({"protocol": MECHANISM_ID, "materials": STORE.state_protocol(),
                                  "identity": STORE.design()["identity"], "providers": provider_info(),
                                  "labels": MECHANISM_LABELS, "rule": RULE,
                                  "batches": mechanism_batches(STORE.trials())})
            if path in ("/api/mechanism/export.json", "/api/mechanism/export.csv"):
                batch = parse_qs(urlsplit(self.path).query).get("batch_id", [""])[0]
                report = summarize_mechanism(STORE.trials(), batch)
                if path.endswith(".csv"):
                    return self.send(csv_export(report["records"]), mime="text/csv; charset=utf-8",
                                     attachment="mechanism-trials.csv")
                return self.send(report, attachment="mechanism-evidence.json")
            if path == "/api/state/bootstrap":
                datasets = [{k: v for k, v in d.items() if k != "rows"} for d in STORE.state_benchmarks()]
                return self.send({"protocol": STORE.state_protocol(), "identity": STORE.design()["identity"],
                                  "providers": provider_info(), "labels": STATE_LABELS, "variants": VARIANTS,
                                  "benchmarks": datasets, "coder_version": CODER_VERSION})
            if path == "/api/state/export.json":
                return self.send({"protocol": STORE.state_protocol(), "records": [r for r in STORE.trials() if r.get("protocol") == PROTOCOL_ID]}, attachment="state-pilot.json")
            if path == "/api/state/export.csv":
                return self.send(csv_export([r for r in STORE.trials() if r.get("protocol") == PROTOCOL_ID]), mime="text/csv; charset=utf-8", attachment="state-pilot.csv")
            if path == "/api/state/human-template.csv":
                return self.send("\ufeffparticipant_id,anxiety_score,anxiety_group,scenario_id,interpretation,action\n", mime="text/csv; charset=utf-8", attachment="human-template.csv")
            if path == "/api/state/human/export.json":
                return self.send(STORE.state_benchmarks(), attachment="human-reference-datasets.json")
            if path == "/api/bootstrap":
                return self.send({"design": STORE.design(), "conditions": CONDITIONS,
                                  "has_api_key": not offline_mode() and bool(os.getenv("OPENAI_API_KEY")),
                                  "default_model": os.getenv("OPENAI_MODEL", "gpt-6-luna"),
                                  "providers": provider_info(),
                                  "human_count": STORE.human_count()})
            if path == "/api/providers":
                return self.send([{**info, "status": PROVIDER_TESTS.get(info["id"], {}).get("status", "未配置" if not info["configured"] else None)} for info in provider_info()])
            if path == "/api/trials":
                return self.send([r for r in STORE.trials() if r.get("protocol") not in (PROTOCOL_ID, MECHANISM_ID, ABLATION_ID)])
            if path.startswith("/api/jobs/"):
                return self.send(JOBS.get(path.rsplit("/", 1)[-1]))
            if path == "/api/export.json":
                return self.send({"warning": "MOCK_NOT_LLM 不是研究证据", "records": STORE.trials()},
                                 attachment="context-memory-trials.json")
            if path == "/api/export.csv":
                return self.send(csv_export(STORE.trials()), mime="text/csv; charset=utf-8", attachment="context-memory-trials.csv")
            assets = {"/ablation": ("web/unified.html", "text/html; charset=utf-8"),
                      "/history.js": ("web/history.js", "application/javascript; charset=utf-8"),
                      "/history.css": ("web/history.css", "text/css; charset=utf-8"),
                      "/ablation.js": ("web/ablation.js", "application/javascript; charset=utf-8"),
                      "/ablation.css": ("web/ablation.css", "text/css; charset=utf-8"),
                      "/ablation-protocol.md": ("ABLATION_DEMO.md", "text/plain; charset=utf-8"),
                      "/": ("web/unified.html", "text/html; charset=utf-8"),
                      "/unified.js": ("web/unified.js", "application/javascript; charset=utf-8"),
                      "/unified.css": ("web/unified.css", "text/css; charset=utf-8"),
                      "/study": ("web/study.html", "text/html; charset=utf-8"),
                      "/mechanism.js": ("web/mechanism.js", "application/javascript; charset=utf-8"),
                      "/mechanism.css": ("web/mechanism.css", "text/css; charset=utf-8"),
                      "/mechanism-protocol.md": ("MECHANISM_DEMO.md", "text/plain; charset=utf-8"),
                      "/workbench": ("web/index.html", "text/html; charset=utf-8"),
                      "/study.js": ("web/study.js", "application/javascript; charset=utf-8"),
                      "/study.css": ("web/study.css", "text/css; charset=utf-8"),
                      "/study-protocol.md": ("STUDY_DESIGN.md", "text/plain; charset=utf-8"),
                      "/app.js": ("web/app.js", "application/javascript; charset=utf-8"),
                      "/multi.js": ("web/multi.js", "application/javascript; charset=utf-8"),
                      "/style.css": ("web/style.css", "text/css; charset=utf-8")}
            assets["/multi.css"] = ("web/multi.css", "text/css; charset=utf-8")
            assets["/demo.css"] = ("web/demo.css", "text/css; charset=utf-8")
            for document in ("DATA_RECOVERY_REPORT", "PROMPT_AUDIT", "PROMPT_PROPOSALS", "RESEARCH_PITCH", "TEST_REPORT"):
                assets["/" + document + ".md"] = (document + ".md", "text/plain; charset=utf-8")
            if path in assets:
                rel, mime = assets[path]
                return self.send((ROOT / rel).read_bytes(), mime=mime)
            return self.send({"error": "Not Found"}, 404)
        except ValueError as exc:
            return self.send({"error": str(exc)}, 404)

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= (MAX_IMPORT_BODY if path.startswith("/api/history/import") else MAX_BODY):
                raise ValueError("请求正文为空或过大")
            data = json.loads(self.rfile.read(size))
            if path in ("/api/history/import/preview", "/api/history/import/commit"):
                # Parse the file on Python's side. JS JSON.parse rounds 64-bit seeds
                # and converts 1.0 to 1, which breaks exact historical recovery.
                document = history.parse_import_json(data["document_json"]) if "document_json" in data else data.get("document")
                return self.send(history.import_records(STORE, document,
                                 commit=path.endswith("/commit"), expected_digest=data.get("digest")))
            if path == "/api/prompts":
                return self.send(prompt_registry.save_bundle(STORE, data), 201)
            if path == "/api/prompts/preview":
                bundle = data.get("bundle") or prompt_registry.get_bundle(STORE, data.get("version"))
                return self.send(prompt_registry.preview(bundle, data.get("name", "林知"),
                    data.get("identity", "20 岁大学生"), data.get("scenario", "你向一位同学发出周末见面的邀请，对方已读但暂未回复。"),
                    data.get("owner", "林知"), data.get("events", "林知上周与同学一起完成了课堂练习。"), data.get("response", "尚无模型输出")))
            if path == "/api/ablation/report":
                return self.send(summarize_ablation(STORE.trials(), data.get("batch_id")))
            if path == "/api/mechanism/report":
                return self.send(summarize_mechanism(STORE.trials(), data.get("batch_id")))
            if path == "/api/state/protocol":
                return self.send(STORE.save_state_protocol(data))
            if path == "/api/ablation/preview":
                preview_request = {**data, "protocol": ABLATION_ID, "mode": "mock", "repeats": 1}
                prepared = plan(STORE.design(), preview_request, STORE.state_protocol())
                matching = [t for t in prepared["tasks"] if t["condition"] == data.get("preview_condition")
                            and t["ablation_format"] == data.get("preview_format")]
                if len(matching) != 1:
                    raise ValueError("请选择需要预览的记忆条件与输出格式")
                task = matching[0]
                return self.send(role_messages(STORE.design(), task["scenario"], task["memories"],
                                               output_mode=task["ablation_format"],
                                               memory_source=task["memory_source"]))
            if path in ("/api/state/preview", "/api/mechanism/preview"):
                # The preview is one selected state; the run still requires all three.
                preview_request = {**data, "protocol": PROTOCOL_ID, "mode": "mock", "repeats": 1}
                prepared = plan(STORE.design(), preview_request, STORE.state_protocol())
                if len(prepared["tasks"]) != 1:
                    raise ValueError("预览应选择单一条件、情境和材料版本")
                task = prepared["tasks"][0]
                return self.send(role_messages(STORE.design(), task["scenario"], task["memories"],
                                               structured=path == "/api/mechanism/preview"))
            if path == "/api/state/report":
                benchmark = None
                if data.get("benchmark_id"):
                    benchmark = next((x for x in STORE.state_benchmarks() if x["id"] == data["benchmark_id"]), None)
                    if benchmark is None:
                        raise ValueError("找不到人类参照数据集")
                return self.send(summarize_states(STORE.trials(), data.get("source", "MOCK_NOT_LLM"), data.get("filters"), benchmark))
            if path == "/api/state/human/import":
                result = STORE.import_state_benchmark(data)
                return self.send({k: v for k, v in result.items() if k != "rows"})
            if path == "/api/design":
                return self.send(STORE.save_design(data))
            if path == "/api/preview":
                d = STORE.design()
                scenario = next((s for s in d["scenarios"] if s["id"] == data.get("scenario_id")), None)
                if scenario is None:
                    raise ValueError("未知情境")
                condition = data.get("condition")
                if condition not in CONDITIONS:
                    raise ValueError("未知条件")
                ids = data.get("memory_ids")
                selected = [] if condition == "baseline" else [m for m in d["memories"] if m["category"] == condition and (ids is None or m["id"] in ids)]
                if condition != "baseline" and not selected:
                    raise ValueError("该条件没有选中记忆")
                return self.send(role_messages(d, scenario, selected))
            if path == "/api/estimate":
                p = plan(STORE.design(), data, STORE.state_protocol() if data.get("protocol") in (PROTOCOL_ID, MECHANISM_ID, ABLATION_ID) else None)
                return self.send({"role_calls": p["calls"], "coding_calls": p["coding_calls"],
                    "concurrency": p["concurrency"], "providers": sorted({m.provider for m in p["models"]}),
                    "warning": "API 费用随模型、上下文和输出长度变化；请核对供应商当前价格。"})
            if path == "/api/provider-test":
                if offline_mode():
                    raise ValueError("离线模式禁止连接测试")
                spec = make_spec(data.get("model_spec"))
                if not os.getenv(PROVIDERS[spec.provider]["env"], "").strip():
                    PROVIDER_TESTS[spec.provider] = {"status": "未配置"}
                    raise ValueError("该 Provider 的环境变量密钥未配置")
                try:
                    answer, meta = call(spec, [{"role": "user", "content": "请只回复：连接成功"}], timeout=20, attempts=1)
                    PROVIDER_TESTS[spec.provider] = {"status": "可用"}
                    return self.send({"status": "可用", "provider": spec.provider, "model": spec.model,
                                      "latency_ms": meta["latency_ms"], "usage": meta["usage"]})
                except Exception as exc:
                    PROVIDER_TESTS[spec.provider] = {"status": "失败"}
                    return self.send({"status": "失败", "error": str(exc)[:350]}, 502)
            if path == "/api/jobs":
                return self.send(JOBS.start(data), 202)
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                return self.send(JOBS.cancel(path.split("/")[-2]))
            if path.startswith("/api/trials/") and path.endswith("/review"):
                c = validate_coding(data.get("coding"))
                return self.send(STORE.review(path.split("/")[-2], c, str(data.get("note", ""))[:1000]))
            if path == "/api/human/import":
                return self.send({"imported": STORE.import_human(data.get("csv", "")), "human_count": STORE.human_count()})
            if path == "/api/analysis":
                source = data.get("source", "LIVE_LLM_API")
                if source not in ("LIVE_LLM_API", "MOCK_NOT_LLM"):
                    raise ValueError("来源无效")
                return self.send(summarize([r for r in STORE.trials() if r.get("protocol") not in (PROTOCOL_ID, MECHANISM_ID, ABLATION_ID)], source, data.get("filters")))
            if path == "/api/model-analysis":
                source = data.get("source", "LIVE_LLM_API")
                if source not in ("LIVE_LLM_API", "MOCK_NOT_LLM"):
                    raise ValueError("来源无效")
                return self.send(model_comparison([r for r in STORE.trials() if r.get("protocol") not in (PROTOCOL_ID, MECHANISM_ID, ABLATION_ID)], source, data.get("filters")))
            return self.send({"error": "Not Found"}, 404)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return self.send({"error": str(exc)}, 400)
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return self.send({"error": str(exc)}, 502)

    def log_message(self, format, *args):
        sys.stderr.write("[web] " + format % args + "\n")


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Do not read credentials; prohibit all paid API calls")
    args = parser.parse_args()
    if args.offline:
        os.environ["SOS_OFFLINE"] = "1"
    if not offline_mode():
        load_local_keys(ROOT / ".env")
    server = LocalServer(("127.0.0.1", args.port), Handler)
    print(f"SOS Context Memory Pilot: http://127.0.0.1:{args.port}")
    print(f"Database: {STORE.path} | revision: {RUNNING_REVISION} | offline: {offline_mode()}")
    if args.open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
