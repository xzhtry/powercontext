"""根据开发任务，从 seekdb 中选择规格、代码与测试，形成开发上下文。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sddctx import db
from sddctx.config import DEMO_APP
from sddctx.util import content_hash, tokens, utc_now

MAX_SPECS = 10
MAX_CODE = 4
MAX_TESTS = 18


def load_task(path: str | Path) -> dict[str, Any]:
    task = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(task, dict):
        raise ValueError("任务文件必须是 JSON 对象")
    for key in ("task_id", "title", "description"):
        if not task.get(key):
            raise ValueError(f"任务文件缺少字段：{key}")
    return task


def _query_text(task: dict[str, Any]) -> str:
    parts = [task["title"], task["description"]]
    parts.extend(str(item) for item in task.get("acceptance", []))
    return " ".join(parts)


def _tags(raw: str) -> list[str]:
    return [item for item in raw.split(";") if item]


def _source(row: dict[str, Any], root: Path) -> dict[str, Any]:
    """校验来源文件与行号真实存在，并给出 snippet 是否仍然新鲜。"""

    path = root / row["path"]
    exists = path.is_file()
    fresh = False
    if exists:
        lines = path.read_text(encoding="utf-8").splitlines()
        start, end = int(row["line_start"]), int(row["line_end"])
        if 1 <= start <= end <= len(lines):
            snippet = "\n".join(lines[start - 1 : end])
            fresh = content_hash(snippet) == row["content_hash"]
    return {
        "material_id": row["material_id"],
        "material_key": row["material_key"],
        "path": row["path"],
        "lines": [row["line_start"], row["line_end"]],
        "content_hash": row["content_hash"],
        "file_exists": exists,
        "fresh": fresh,
    }


def _spec_item(row: dict[str, Any], root: Path) -> dict[str, Any]:
    return {
        "id": row["doc_id"],
        "section_id": row["section_id"],
        "version": row["version"],
        "title": row["title"],
        "path": row["path"],
        "lines": [row["line_start"], row["line_end"]],
        "text": row["body"],
        "score": round(float(row.get("fts_score", 0.0)) + float(row.get("boost", 0.0)), 4),
        "source": _source(row, root),
    }


def _code_item(row: dict[str, Any], root: Path, score: float) -> dict[str, Any]:
    return {
        "path": row["path"],
        "symbol": row["symbol"],
        "lines": [row["line_start"], row["line_end"]],
        "snippet": row["body"],
        "score": round(score, 4),
        "source": _source(row, root),
    }


def _test_item(row: dict[str, Any], root: Path, score: float) -> dict[str, Any]:
    tags = _tags(row["tags"])
    covers = [tag.split("=", 1)[1] for tag in tags if tag.startswith("covers=")]
    role = next((tag.split("=", 1)[1] for tag in tags if tag.startswith("role=")), "regression")
    return {
        "path": row["path"],
        "symbol": row["symbol"],
        "role": role,
        "covers": covers,
        "lines": [row["line_start"], row["line_end"]],
        "snippet": row["body"],
        "score": round(score, 4),
        "source": _source(row, root),
    }


def build_context(
    task: dict[str, Any],
    *,
    db_path: Path,
    root: Path = DEMO_APP,
    pc_state: dict[str, Any] | None = None,
    record_run: bool = True,
) -> dict[str, Any]:
    query = _query_text(task)
    boost_terms = tokens(query)
    trace: list[dict[str, Any]] = []
    with db.open_db(db_path) as connection:
        hits = db.search_fts(connection, query, boost_terms=boost_terms, limit=120, trace=trace)
        spec_hits = [row for row in hits if row["kind"] == "spec"]
        code_hits = [row for row in hits if row["kind"] == "code"]
        test_hits = [row for row in hits if row["kind"] == "test"]

        specs: list[dict[str, Any]] = []
        seen_sections: set[str] = set()
        for row in spec_hits:
            if row["section_id"] in seen_sections:
                continue
            seen_sections.add(row["section_id"])
            specs.append(_spec_item(row, root))
            if len(specs) >= MAX_SPECS:
                break

        selected_sections = {item["section_id"] for item in specs}
        applies: list[str] = []
        for row in spec_hits:
            if row["section_id"] not in selected_sections:
                continue
            for tag in _tags(row["tags"]):
                if tag.startswith("applies="):
                    applies.append(tag.split("=", 1)[1])

        symbol_keys: list[str] = []
        for target in applies:
            parts = target.split(".")
            if len(parts) >= 2:
                symbol_keys.append(f"symbol_key={'.'.join(parts[-2:])}")
        symbol_rows = db.find_by_tags(connection, kind="code", tags=symbol_keys, trace=trace)

        code_items: list[dict[str, Any]] = []
        seen_code: set[tuple[str, str]] = set()
        for row in symbol_rows:
            key = (row["path"], row["symbol"])
            if key in seen_code:
                continue
            seen_code.add(key)
            code_items.append(_code_item(row, root, 3.0))
        if len(code_items) < 3:
            # 仅当规格指向的符号不足时，才用全文检索补充同模块代码，避免无关符号。
            referenced_modules = {target.split(".")[-2] for target in applies if "." in target}
            for row in code_hits:
                module = row["path"].rsplit("/", 1)[-1].removesuffix(".py")
                key = (row["path"], row["symbol"])
                if module not in referenced_modules or key in seen_code:
                    continue
                seen_code.add(key)
                code_items.append(_code_item(row, root, float(row["fts_score"])))
                if len(code_items) >= MAX_CODE:
                    break
        code_items = code_items[:MAX_CODE]

        cover_tags = [f"covers={section}" for section in selected_sections]
        test_rows = db.find_by_tags(connection, kind="test", tags=cover_tags, trace=trace)
        test_items: list[dict[str, Any]] = []
        seen_tests: set[str] = set()
        for row in test_rows:
            if row["symbol"] in seen_tests:
                continue
            seen_tests.add(row["symbol"])
            covers = [tag.split("=", 1)[1] for tag in _tags(row["tags"]) if tag.startswith("covers=")]
            overlap = len(set(covers) & selected_sections)
            test_items.append(_test_item(row, root, 1.0 + 0.5 * overlap))
        for row in test_hits:
            if row["symbol"] in seen_tests:
                continue
            seen_tests.add(row["symbol"])
            test_items.append(_test_item(row, root, float(row["fts_score"])))
            if len(test_items) >= MAX_TESTS:
                break
        test_items.sort(key=lambda item: (item["role"] != "target", -item["score"]))
        test_items = test_items[:MAX_TESTS]

        spec_ids = [f"{item['id']}#{item['section_id']}" for item in specs]
        digest = content_hash(
            json.dumps(
                {
                    "specs": spec_ids,
                    "code": [f"{item['path']}::{item['symbol']}" for item in code_items],
                    "tests": [f"{item['path']}::{item['symbol']}" for item in test_items],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        run_id = f"ctx-{uuid4().hex[:12]}"
        if record_run:
            db.log_context_run(
                connection,
                {
                    "run_id": run_id,
                    "task_id": task["task_id"],
                    "query": query,
                    "selected": json.dumps({"specs": spec_ids, "digest": digest}, ensure_ascii=False),
                    "created_at": utc_now(),
                },
            )
        cursor = connection.cursor()
        cursor.execute("SHOW VARIABLES LIKE 'version'")
        version_row = cursor.fetchall()

    sources = [
        {"kind": "spec", **item["source"]} for item in specs
    ] + [
        {"kind": "code", **item["source"]} for item in code_items
    ] + [
        {"kind": "test", **item["source"]} for item in test_items
    ]
    stale = [source for source in sources if not source["file_exists"] or not source["fresh"]]
    state = pc_state or {
        "status": "empty",
        "source": "powercontext",
        "run_seq": 0,
        "completed": [],
        "pending": [],
        "verifications": [],
    }
    return {
        "schema": "sddctx.context.v1",
        "run_id": run_id,
        "generated_at": utc_now(),
        "task": {
            "task_id": task["task_id"],
            "title": task["title"],
            "description": task["description"],
            "acceptance": task.get("acceptance", []),
        },
        "specs": specs,
        "code": code_items,
        "tests": test_items,
        "state": state,
        "sources": sources,
        "warnings": [] if not stale else [f"{len(stale)} 个来源与当前文件不一致，请重新导入"],
        "db": {
            "engine": "seekdb (OceanBase embedded)",
            "version": version_row[0][1] if version_row else "unknown",
            "query": query,
            "query_trace": trace,
            "rows_considered": len(hits),
            "context_digest": digest,
        },
    }
