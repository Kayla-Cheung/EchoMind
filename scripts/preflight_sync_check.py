"""Read-only sync preflight and privacy boundary check for EchoMind."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FORBIDDEN_TRACKED_PREFIXES = (
    "private_inputs/",
    "private_exports/",
    "papers/",
    "backups/",
)

FORBIDDEN_TRACKED_EXTENSIONS = (
    ".sqlite",
    ".sqlite3",
    ".db",
    ".sav",
    ".spv",
    ".secret",
)


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def check_repo(repo: Path) -> int:
    branch = run_git(repo, "branch", "--show-current").strip() or "DETACHED"
    head = run_git(repo, "rev-parse", "--short", "HEAD").strip()
    porcelain = [line for line in run_git(repo, "status", "--porcelain=v1").splitlines() if line]
    tracked = run_git(repo, "ls-files").splitlines()

    violations: list[str] = []
    for rel in tracked:
        norm = rel.replace("\\", "/")
        if norm == ".env" or (norm.startswith(".env.") and norm != ".env.example"):
            violations.append(f"forbidden env file tracked: {norm}")
        if norm.startswith(FORBIDDEN_TRACKED_PREFIXES):
            violations.append(f"forbidden private path tracked: {norm}")
        if norm.endswith(FORBIDDEN_TRACKED_EXTENSIONS):
            violations.append(f"forbidden binary/db tracked: {norm}")

    print(f"branch={branch} head={head} dirty_entries={len(porcelain)} tracked_files={len(tracked)}")
    if violations:
        for item in violations:
            print(f"VIOLATION: {item}")
        return 1
    print("privacy_boundary=OK")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    sys.exit(check_repo(target))
