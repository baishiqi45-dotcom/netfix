"""netfix constants"""
from pathlib import Path
import sys

VERSION = "0.2.0"
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    REPO_ROOT = Path(sys._MEIPASS)
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
RULES_DIR = REPO_ROOT / "rules"
CASES_DIR = REPO_ROOT / "cases"
JOURNAL_DIR = Path.home() / ".netfix"
JOURNAL_FILE = JOURNAL_DIR / "journal.jsonl"

# Common proxy/API ports on macOS
COMMON_PROXY_PORTS = [1080, 10808, 10809, 7890, 7891, 7892, 9090, 9097, 8080, 8443]

# Endpoints we care about for Codex/AI work
CODEX_ENDPOINTS = [
    {"name": "openai_api", "url": "https://api.openai.com", "path": "/v1/models", "expect": 200},
    {"name": "openai_chat", "url": "https://chat.openai.com", "path": "/", "expect": 200},
    {"name": "github", "url": "https://github.com", "path": "/", "expect": 200},
    {"name": "github_api", "url": "https://api.github.com", "path": "/", "expect": 200},
]

# Generic endpoints for general network health
GENERIC_ENDPOINTS = [
    {"name": "cloudflare", "url": "https://1.1.1.1", "path": "/", "expect": 200},
    {"name": "google", "url": "https://www.google.com", "path": "/generate_204", "expect": 204},
]

# Maps v2rayN ConfigType integer to human-readable protocol name.
# Observed on the user's environment: 4 = SOCKS, 10 = HTTP.
# Unknown types fall back to "type-{n}" so we never mislabel.
V2RAYN_CONFIG_TYPES = {
    1: "vmess",
    2: "shadowsocks",
    4: "socks",
    5: "http",
    6: "trojan",
    7: "vless",
    10: "http",
}
