"""上下文模块的核心行为测试（需要 Linux + pylibseekdb）。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sddctx import ingest
from sddctx.config import PACKAGE_ROOT
from sddctx.retrieval import build_context, load_task

BEFORE = PACKAGE_ROOT / "snapshots" / "before"
TASK = load_task(PACKAGE_ROOT / "samples" / "TASK-101.json")


def _import(root: Path, db_path: Path) -> None:
    ingest.import_materials(ingest.collect_materials(root), db_path=db_path)


def test_context_selects_required_specs_code_and_tests(tmp_path):
    db_path = tmp_path / "seekdb"
    _import(BEFORE, db_path)
    context = build_context(TASK, db_path=db_path, root=BEFORE, record_run=False)

    section_ids = {item["section_id"] for item in context["specs"]}
    assert {"REQ-INV-004.2", "REQ-INV-004.3", "REQ-INV-004.4"} <= section_ids
    assert "API-INV-002.3" in section_ids

    symbols = {item["symbol"] for item in context["code"]}
    assert {"list_invoices", "build_parser", "_run_list"} <= symbols

    targets = [item for item in context["tests"] if item["role"] == "target"]
    assert len(targets) == 7
    assert all(item["source"]["file_exists"] for item in context["tests"])
    assert all(item["source"]["fresh"] for item in context["tests"])
    assert context["sources"]
    assert context["db"]["query_trace"]


def test_context_uses_updated_spec_after_reimport(tmp_path):
    app = tmp_path / "app"
    shutil.copytree(BEFORE, app, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    db_path = tmp_path / "seekdb"
    _import(app, db_path)

    spec = app / "specs" / "REQ-INV-004-invoice-list-filtering.md"
    original = spec.read_text(encoding="utf-8")
    updated = original.replace("version: 1", "version: 2", 1).replace(
        "- 金额比较必须使用十进制精确值，禁止转换为二进制浮点数后再比较。",
        "- 金额比较必须使用十进制精确值，禁止转换为二进制浮点数后再比较。\n- v2 新增：min_amount 为 0 时等价于不过滤非负金额。",
    )
    spec.write_text(updated, encoding="utf-8")
    _import(app, db_path)

    context = build_context(TASK, db_path=db_path, root=app, record_run=False)
    item = next(item for item in context["specs"] if item["section_id"] == "REQ-INV-004.2")
    assert item["version"] == 2
    assert "v2 新增" in item["text"]

    spec.write_text(original, encoding="utf-8")
    _import(app, db_path)
    context = build_context(TASK, db_path=db_path, root=app, record_run=False)
    assert next(item for item in context["specs"] if item["section_id"] == "REQ-INV-004.2")["version"] == 1


def test_import_records_material_counts(tmp_path):
    summary = ingest.import_materials(ingest.collect_materials(BEFORE), db_path=tmp_path / "seekdb")
    assert summary["count"] == summary["specs"] + summary["code"] + summary["tests"]
    assert summary["specs"] >= 10
    assert summary["tests"] >= 20
