"""通用工具：SQL 字面量、哈希、时间与 JSON 读写。"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sql_literal(value: str) -> str:
    """把 Python 字符串转成 seekdb 可接受的 SQL 字面量。

    seekdb 的 Python 绑定只接受完整 SQL 字符串（不支持参数占位符），
    因此这里统一做转义：反斜杠、单引号、NUL。
    """

    text = str(value).replace("\\", "\\\\").replace("'", "''").replace("\x00", "")
    return "'" + text + "'"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def tokens(text: str) -> list[str]:
    """提取用于检索的标识符与中文词组（去重保序）。"""

    seen: dict[str, None] = {}
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]{2,}", text):
        token = match.group(0).lower()
        if token not in {"the", "and", "for", "with", "from", "this", "that"}:
            seen.setdefault(token, None)
    for match in re.finditer(r"[\u4e00-\u9fff]{2,6}", text):
        token = match.group(0)
        seen.setdefault(token, None)
    return list(seen)
