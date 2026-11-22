"""Load local API keys without exposing them in logs or replacing process settings."""
import os
from pathlib import Path


KEY_NAMES = frozenset({
    "DEEPSEEK_API_KEY", "MINIMAX_API_KEY", "MIMO_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
})


def load_local_keys(path):
    path = Path(path)
    if not path.is_file():
        return
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f".env 第 {number} 行缺少等号")
        name, value = (part.strip() for part in line.split("=", 1))
        if name not in KEY_NAMES:
            raise ValueError(f".env 第 {number} 行包含未知变量名：{name}")
        if value.startswith(('"', "'")) and value.endswith(value[0]) and len(value) >= 2:
            value = value[1:-1]
        if value and not os.environ.get(name):
            os.environ[name] = value
