"""运行时配置。

所有可写数据都放在 Linux 文件系统（默认 ``~/.local/share/grudge-inn``）。
seekdb 的嵌入式引擎无法在 WSL 的 ``/mnt/*``（drvfs）上打开数据库。
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
APP_DIR = PACKAGE_DIR.parent


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser() if raw else default


RUNTIME_DIR = _env_path("GRUDGE_INN_RUNTIME", Path.home() / ".local" / "share" / "grudge-inn")
SEEKDB_DIR = _env_path("GRUDGE_INN_SEEKDB", RUNTIME_DIR / "seekdb")
DATABASE_PATH = SEEKDB_DIR
SCOPE_FILE = RUNTIME_DIR / "powercontext-scopes.json"

HOST = os.getenv("GRUDGE_INN_HOST", "0.0.0.0")
PORT = int(os.getenv("GRUDGE_INN_PORT", "8787"))
POWERCONTEXT_URL = os.getenv("GRUDGE_INN_POWERCONTEXT_URL", "http://127.0.0.1:8766").rstrip("/")
POWERCONTEXT_TIMEOUT = float(os.getenv("GRUDGE_INN_POWERCONTEXT_TIMEOUT", "20"))

MAX_ACTION_CHARS = 500
MAX_NARRATIVE_CHARS = 4000
MAX_PLAYER_ID_CHARS = 64

CARDS_FILE = PACKAGE_DIR / "data" / "cards.json"


def ensure_runtime_dirs() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SEEKDB_DIR.mkdir(parents=True, exist_ok=True)
