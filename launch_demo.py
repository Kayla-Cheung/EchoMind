"""Reopen an existing local demo or start it on its dedicated port."""
import json
import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

URL = "http://127.0.0.1:8768"


def main():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(URL + "/api/health", timeout=2) as response:
            info = json.load(response)
            running = info.get("version") == "research-repair-v1"
            if running:
                # No server import: checking the revision must not open any database.
                import hashlib
                root = Path(__file__).resolve().parent
                paths = sorted(root.glob("*.py")) + sorted((root / "web").glob("*.*"))
                local = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in paths)).hexdigest()[:16]
                if info.get("code_revision") != local:
                    print("Source files changed. Stop the existing server and restart; history remains in: " + info.get("database", "unknown"))
                    return 1
    except (OSError, ValueError):
        running = False
    if running:
        webbrowser.open(URL)
        print("Demo is already running: " + URL)
        return 0
    return subprocess.call([sys.executable, "-u", str(Path(__file__).with_name("server.py")),
                            "--port", "8768", "--open-browser"])


if __name__ == "__main__":
    raise SystemExit(main())
