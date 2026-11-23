#!/usr/bin/env python3
"""
EchoMind - Open-Science Human Dataset Fetcher (OSF node: b35da)
Downloads open files from OSF with TLS verification and path-traversal checks.
Does NOT synthesize, hardcode, or fabricate human normative percentages for EchoMind scenarios.
"""
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BENCHMARK_DIR = ROOT / "data" / "human_benchmarks"
OSF_API_URL = "https://api.osf.io/v2/nodes/b35da/files/osfstorage/"
HEADERS = {
    "User-Agent": "EchoMind-Research-Tool/1.0",
    "Accept": "application/json",
}


def _safe_child_path(base_dir: Path, name: str) -> Path:
    """Reject empty names, path separators, or traversal outside base_dir."""
    if not name or name in (".", "..") or "/" in name or "\\" in name or ":" in name:
        raise ValueError(f"不安全的远端文件名：{name!r}")
    base_resolved = base_dir.resolve()
    target = (base_resolved / name).resolve()
    if not target.is_relative_to(base_resolved):
        raise ValueError(f"检测到路径穿越：{name!r}")
    return target


def fetch_osf_files_recursive(api_url: str, current_dir: Path, depth: int = 0):
    """Recursively fetch public OSF files using verified HTTPS."""
    if depth > 4:
        return []

    downloaded = []
    ctx = ssl.create_default_context()
    req = urllib.request.Request(api_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"[!] 无法访问 OSF API ({exc})；未生成任何合成人类常模。", file=sys.stderr)
        return []

    for item in payload.get("data", []):
        attrs = item.get("attributes", {})
        name = attrs.get("name", "")
        kind = attrs.get("kind", "file")
        links = item.get("links", {})
        try:
            target = _safe_child_path(current_dir, name)
        except ValueError as exc:
            print(f"[!] 跳过不安全条目：{exc}", file=sys.stderr)
            continue

        if kind == "folder":
            target.mkdir(parents=True, exist_ok=True)
            files_href = (
                item.get("relationships", {})
                .get("files", {})
                .get("links", {})
                .get("related", {})
                .get("href")
            )
            if files_href:
                downloaded.extend(fetch_osf_files_recursive(files_href, target, depth + 1))
        elif kind == "file":
            download_url = links.get("download")
            if download_url and download_url.startswith("https://"):
                try:
                    dl_req = urllib.request.Request(download_url, headers=HEADERS)
                    with urllib.request.urlopen(dl_req, timeout=30, context=ctx) as dl_resp:
                        target.write_bytes(dl_resp.read())
                    downloaded.append(str(target.relative_to(BENCHMARK_DIR.resolve())))
                except Exception as dl_err:
                    print(f"[!] 下载跳过 ({dl_err}): {name}", file=sys.stderr)

    return downloaded


def main():
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    print("EchoMind · OSF 公开原始资料抓取工具（仅下载原始文件，不生成硬编码人类常模）")
    files = fetch_osf_files_recursive(OSF_API_URL, BENCHMARK_DIR)
    manifest = {
        "source": "https://osf.io/b35da/",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "downloaded_files": files,
        "notice": (
            "本目录仅用于研究者本地查阅公开论文与开源原始数据集，禁止将受版权保护的 PDF "
            "推送到公开仓库，也禁止未经同范式逐题对齐即宣称人类拟合。"
        ),
    }
    manifest_path = BENCHMARK_DIR / "osf_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[√] 已写入清单：{manifest_path.resolve()}（本次下载 {len(files)} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
