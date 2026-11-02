"""seekdb（嵌入式）存储层。

seekdb 是 OceanBase 的嵌入式发行版，Python 绑定 ``pylibseekdb`` 只支持 Linux。
本模块负责建表、导入工程资料、全文检索与运行记录。
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pylibseekdb as seekdb

from sddctx.util import content_hash, sql_literal, utc_now

_LOCK = threading.Lock()
_OPEN_PATH: str | None = None

SCHEMA = [
    """
    CREATE TABLE materials (
        material_id INT AUTO_INCREMENT PRIMARY KEY,
        material_key VARCHAR(512) NOT NULL,
        doc_id VARCHAR(128) NOT NULL,
        section_id VARCHAR(128) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        path VARCHAR(1024) NOT NULL,
        symbol VARCHAR(256) NOT NULL,
        version INT NOT NULL,
        status VARCHAR(16) NOT NULL,
        title VARCHAR(1024) NOT NULL,
        body TEXT NOT NULL,
        keywords TEXT NOT NULL,
        tags TEXT NOT NULL,
        line_start INT NOT NULL,
        line_end INT NOT NULL,
        content_hash VARCHAR(64) NOT NULL,
        imported_at VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_material_key (material_key)
    )
    """,
    "CREATE FULLTEXT INDEX ft_materials ON materials(title, body, keywords) WITH PARSER ngram",
    """
    CREATE TABLE context_runs (
        run_id VARCHAR(64) PRIMARY KEY,
        task_id VARCHAR(128) NOT NULL,
        query TEXT NOT NULL,
        selected TEXT NOT NULL,
        created_at VARCHAR(40) NOT NULL
    )
    """,
]


def _ensure_open(path: Path) -> None:
    global _OPEN_PATH
    target = str(path)
    if _OPEN_PATH == target:
        return
    if _OPEN_PATH is not None:
        seekdb.close()
        _OPEN_PATH = None
    path.mkdir(parents=True, exist_ok=True)
    try:
        seekdb.open(target)
    except Exception as error:  # pragma: no cover - 依赖宿主文件系统
        raise RuntimeError(
            f"无法在 {target} 打开 seekdb。WSL 的 /mnt/* (drvfs) 不受支持，"
            "请把 SDDCTX_RUNTIME 指到 Linux 文件系统路径。"
        ) from error
    _OPEN_PATH = target


@contextlib.contextmanager
def open_db(path: Path) -> Iterator[Any]:
    """打开数据库连接。嵌入式引擎在进程内只允许一份实例。"""

    with _LOCK:
        _ensure_open(path)
        connection = seekdb.connect()
    try:
        yield connection
    finally:
        with _LOCK:
            with contextlib.suppress(Exception):
                connection.close()


def rebuild_schema(connection: Any) -> None:
    cursor = connection.cursor()
    cursor.execute("DROP TABLE IF EXISTS materials")
    for statement in SCHEMA[:2]:
        cursor.execute(statement)
    cursor.execute("CREATE TABLE IF NOT EXISTS context_runs ("
                   "run_id VARCHAR(64) PRIMARY KEY,"
                   "task_id VARCHAR(128) NOT NULL,"
                   "query TEXT NOT NULL,"
                   "selected TEXT NOT NULL,"
                   "created_at VARCHAR(40) NOT NULL)")
    connection.commit()


def insert_material(connection: Any, record: dict[str, Any]) -> int:
    cursor = connection.cursor()
    columns = [
        "material_key",
        "doc_id",
        "section_id",
        "kind",
        "path",
        "symbol",
        "version",
        "status",
        "title",
        "body",
        "keywords",
        "tags",
        "line_start",
        "line_end",
        "content_hash",
        "imported_at",
    ]
    values = ", ".join(sql_literal(str(record[column])) for column in columns)
    cursor.execute(f"INSERT INTO materials ({', '.join(columns)}) VALUES ({values})")
    connection.commit()
    cursor.execute("SELECT LAST_INSERT_ID()")
    return int(cursor.fetchall()[0][0])


def material_count(connection: Any) -> int:
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM materials")
    return int(cursor.fetchall()[0][0])


def search_fts(
    connection: Any,
    query: str,
    *,
    boost_terms: list[str],
    limit: int = 80,
    trace: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """全文检索并叠加标题/正文命中加权。"""

    if not query.strip():
        return []
    literal = sql_literal(query)
    boost_parts = ["0"]
    for term in boost_terms[:6]:
        token = sql_literal(f"%{term}%")
        boost_parts.append(f"(CASE WHEN title LIKE {token} THEN 4 ELSE 0 END)")
        boost_parts.append(f"(CASE WHEN body LIKE {token} THEN 1 ELSE 0 END)")
    boost_expr = " + ".join(boost_parts)
    sql = f"""
        SELECT material_id, material_key, doc_id, section_id, kind, path, symbol,
               version, status, title, body, keywords, tags, line_start, line_end,
               content_hash,
               MATCH(title, body, keywords) AGAINST ({literal}) AS fts_score,
               ({boost_expr}) AS boost
        FROM materials
        WHERE status = 'active'
          AND MATCH(title, body, keywords) AGAINST ({literal})
        ORDER BY (MATCH(title, body, keywords) AGAINST ({literal}) + ({boost_expr})) DESC
        LIMIT {int(limit)}
    """
    cursor = connection.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    if trace is not None:
        trace.append({"sql": " ".join(sql.split()), "rows": len(rows), "purpose": "fulltext-search"})
    columns = [
        "material_id",
        "material_key",
        "doc_id",
        "section_id",
        "kind",
        "path",
        "symbol",
        "version",
        "status",
        "title",
        "body",
        "keywords",
        "tags",
        "line_start",
        "line_end",
        "content_hash",
        "fts_score",
        "boost",
    ]
    return [dict(zip(columns, row, strict=True)) for row in rows]


def find_by_tags(
    connection: Any,
    *,
    kind: str,
    tags: list[str],
    trace: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """按标签查找资料，例如规格的 applies / 测试的 covers。"""

    if not tags:
        return []
    likes = " OR ".join(f"tags LIKE {sql_literal('%' + tag + '%')}" for tag in dict.fromkeys(tags))
    sql = f"""
        SELECT material_id, material_key, doc_id, section_id, kind, path, symbol,
               version, status, title, body, keywords, tags, line_start, line_end, content_hash
        FROM materials
        WHERE kind = {sql_literal(kind)} AND status = 'active' AND ({likes})
        ORDER BY material_id
        LIMIT 200
    """
    cursor = connection.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    if trace is not None:
        trace.append({"sql": " ".join(sql.split()), "rows": len(rows), "purpose": f"tag-lookup:{kind}"})
    columns = [
        "material_id",
        "material_key",
        "doc_id",
        "section_id",
        "kind",
        "path",
        "symbol",
        "version",
        "status",
        "title",
        "body",
        "keywords",
        "tags",
        "line_start",
        "line_end",
        "content_hash",
    ]
    return [dict(zip(columns, row, strict=True)) for row in rows]


def log_context_run(connection: Any, run: dict[str, Any]) -> None:
    cursor = connection.cursor()
    values = ", ".join(
        sql_literal(str(run[column])) for column in ("run_id", "task_id", "query", "selected", "created_at")
    )
    cursor.execute(f"INSERT INTO context_runs (run_id, task_id, query, selected, created_at) VALUES ({values})")
    connection.commit()


def list_context_runs(connection: Any, task_id: str | None = None) -> list[dict[str, Any]]:
    cursor = connection.cursor()
    where = "" if task_id is None else f" WHERE task_id = {sql_literal(task_id)}"
    cursor.execute(f"SELECT run_id, task_id, query, selected, created_at FROM context_runs{where} ORDER BY created_at")
    return [
        dict(zip(("run_id", "task_id", "query", "selected", "created_at"), row, strict=True))
        for row in cursor.fetchall()
    ]


def hash_text(text: str) -> str:
    return content_hash(text)


def now() -> str:
    return utc_now()
