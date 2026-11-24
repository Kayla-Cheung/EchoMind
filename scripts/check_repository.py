"""Read-only checks of public files, the experiment index and frozen snapshots."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRS = {"private_inputs", "private_exports", "backups", "papers", "__pycache__", ".venv", "node_modules"}
PUBLIC_DATA = {"scenarios.json", "rr_v05_source_manifest.json"}
CREDENTIALS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
)


def local_path(root: Path, relative: str) -> Path:
    """Do not let a registry entry or symlink escape the selected checkout."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("Expected a nonempty repository-relative POSIX path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or PureWindowsPath(relative).drive or ".." in posix.parts:
        raise ValueError("Path must stay inside the repository")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Resolved path leaves the repository")
    return path


def forbidden_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    name = parts[-1].lower()
    if any(p.lower() in PRIVATE_DIRS for p in parts):
        return True
    if name.startswith(".env") and name != ".env.example":
        return True
    if name in {"rr.csv", "split_salt.txt", "local_paths.json"} or name.startswith(("smoke-live", "rr-real-", "ratings-real-")):
        return True
    if re.search(r"\.(?:sqlite[^/]*|db(?:-.*)?|pdf|zip|sav|spv|log|jsonl|pyc|secret)$", name):
        return True
    if "data" in parts:
        # Only known public configuration/provenance directly inside data/.
        return len(parts) < 2 or parts[-2] != "data" or name not in PUBLIC_DATA
    return False


def public_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, check=True, capture_output=True,
    )
    return sorted(set(result.stdout.decode("utf-8").strip("\0").split("\0")) - {""})


def notebook_errors(data: dict) -> list[str]:
    errors = []
    for index, cell in enumerate(data.get("cells", []), 1):
        if cell.get("cell_type") == "code" and (
            cell.get("outputs") or cell.get("execution_count") is not None
        ):
            errors.append(f"cell {index}: saved output or execution count")
    return errors


def audit(root: Path) -> tuple[list[str], dict]:
    errors = []
    candidates = public_paths(root)
    existing = []
    for relative in candidates:
        try:
            path = local_path(root, relative)
        except ValueError as exc:
            errors.append(f"{relative}: {exc}")
            continue
        if not path.exists():  # A worktree deletion is reviewed separately by Git.
            continue
        existing.append(relative)
        if forbidden_path(relative):
            errors.append(f"{relative}: excluded artifact in public file set")
            continue
        if not path.is_file():
            errors.append(f"{relative}: expected an ordinary public file")
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"{relative}: binary/non-UTF-8 file requires explicit review")
            continue
        if any(pattern.search(content) for pattern in CREDENTIALS):
            errors.append(f"{relative}: possible credential; value withheld")
        if path.suffix == ".ipynb":
            try:
                errors.extend(f"{relative}: {error}" for error in notebook_errors(json.loads(content)))
            except (ValueError, AttributeError, TypeError):
                errors.append(f"{relative}: invalid notebook JSON")

    registry = json.loads((root / "configs/experiments.json").read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1:
        errors.append("Unsupported experiment index schema")
    ids, locations = set(), set()
    for entry in registry["experiments"]:
        if entry["id"] in ids or entry["path"] in locations:
            errors.append("Duplicate experiment ID or directory")
        ids.add(entry["id"])
        locations.add(entry["path"])
        try:
            directory = local_path(root, entry["path"])
            protocol = local_path(directory, entry["protocol"])
            if not directory.is_dir() or not protocol.is_file():
                errors.append(f"{entry['id']}: missing directory/protocol")
        except ValueError as exc:
            errors.append(f"{entry['id']}: {exc}")
    disk_versions = {p.name for p in (root / "experiments").iterdir() if p.is_dir() and not p.name.startswith(".")}
    indexed_versions = {PurePosixPath(p).name for p in locations if p.startswith("experiments/")}
    if disk_versions != indexed_versions:
        errors.append("Experiment directories and index differ")

    lock = json.loads((root / "configs/snapshot-integrity.json").read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1 or lock.get("normalization") != "CRLF_to_LF":
        errors.append("Unsupported snapshot integrity schema/normalization")
    snapshot_files = lock["files"]
    current = {p for p in existing if p.startswith("experiments/")}
    if current != set(snapshot_files):
        errors.append("Snapshot public file set differs from integrity manifest")
    for relative, expected in snapshot_files.items():
        path = local_path(root, relative)
        if not relative.startswith("experiments/") or not path.is_file():
            errors.append(f"{relative}: invalid/missing snapshot file")
        elif hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != expected:
            errors.append(f"{relative}: frozen snapshot changed")
    return errors, {"public_files": len(existing), "snapshot_files": len(snapshot_files), "experiments": len(ids)}


def main() -> int:
    try:
        errors, counts = audit(ROOT)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(f"Repository check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(counts, sort_keys=True))
    for error in errors:
        print("FAIL: " + error, file=sys.stderr)
    print("Repository audit: " + ("FAIL" if errors else "PASS"))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
