"""把规格、代码、测试导入 seekdb。

导入以“全量重建 materials 表”的方式完成，便于规格更新后重新导入：
旧内容被替换，检索只会看到最新导入的版本。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sddctx import db
from sddctx.config import DEMO_APP
from sddctx.util import content_hash, tokens, utc_now, write_json

SPEC_ID_RE = re.compile(r"^([A-Z][A-Z0-9]*-(?:[A-Z0-9]+-)+\d+(?:\.\d+)?)\b")
CODE_SUFFIXES = {".py"}


@dataclass
class Material:
    material_key: str
    doc_id: str
    section_id: str
    kind: str
    path: str
    symbol: str
    version: int
    status: str
    title: str
    body: str
    keywords: str
    tags: list[str] = field(default_factory=list)
    line_start: int = 1
    line_end: int = 1
    content_hash: str = ""

    def to_record(self, imported_at: str) -> dict[str, Any]:
        return {
            "material_key": self.material_key,
            "doc_id": self.doc_id,
            "section_id": self.section_id,
            "kind": self.kind,
            "path": self.path,
            "symbol": self.symbol,
            "version": self.version,
            "status": self.status,
            "title": self.title,
            "body": self.body,
            "keywords": self.keywords,
            "tags": ";".join(self.tags),
            "line_start": self.line_start,
            "line_end": self.line_end,
            "content_hash": self.content_hash or content_hash(self.body),
            "imported_at": imported_at,
        }


def _parse_front_matter(text: str) -> tuple[dict[str, str], int]:
    if not text.startswith("---"):
        return {}, 0
    lines = text.splitlines()
    meta: dict[str, str] = {}
    end = 0
    for index in range(1, len(lines)):
        line = lines[index].strip()
        if line == "---":
            end = index
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    if end == 0:
        return {}, 0
    return meta, end + 1  # 返回正文起始行号（从 1 开始）


def _parse_list(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [item.strip().strip('"').strip("'") for item in raw.split(",") if item.strip()]


def _spec_materials(root: Path) -> list[Material]:
    materials: list[Material] = []
    for path in sorted((root / "specs").rglob("*.md")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        meta, body_start = _parse_front_matter(text)
        doc_id = meta.get("id") or path.stem
        version = int(meta.get("version", "1"))
        status = meta.get("status", "active")
        applies = _parse_list(meta.get("applies_to", ""))
        front_keywords = _parse_list(meta.get("keywords", ""))
        lines = text.splitlines()
        heading_indexes = [i for i, line in enumerate(lines) if line.startswith("## ")]
        for position, index in enumerate(heading_indexes):
            end = heading_indexes[position + 1] - 1 if position + 1 < len(heading_indexes) else len(lines) - 1
            while end > index and not lines[end].strip():
                end -= 1
            heading = lines[index][3:].strip()
            match = SPEC_ID_RE.match(heading)
            section_id = match.group(1) if match else f"{doc_id}.{position + 1}"
            section_text = "\n".join(lines[index : end + 1])
            tags = [f"spec={doc_id}", f"section={section_id}", f"version={version}"]
            for target in applies:
                tags.append(f"applies={target}")
                parts = target.split(".")
                if len(parts) >= 2:
                    tags.append(f"applies={'.'.join(parts[-2:])}")
            keywords = " ".join(front_keywords + tokens(f"{heading}\n{section_text}"))
            materials.append(
                Material(
                    material_key=f"spec:{doc_id}:{section_id}:{version}",
                    doc_id=doc_id,
                    section_id=section_id,
                    kind="spec",
                    path=rel,
                    symbol="",
                    version=version,
                    status=status,
                    title=heading,
                    body=section_text,
                    keywords=keywords,
                    tags=tags,
                    line_start=index + 1,
                    line_end=end + 1,
                    content_hash=content_hash(section_text),
                )
            )
    return materials


def _module_docstring(tree: ast.Module) -> str:
    return ast.get_docstring(tree) or ""


def _code_materials(root: Path) -> list[Material]:
    materials: list[Material] = []
    for path in sorted((root / "src").rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        tree = ast.parse(text)
        module = path.stem
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            snippet = "\n".join(lines[start - 1 : end])
            docstring = ast.get_docstring(node) or ""
            keywords = " ".join(tokens(f"{node.name}\n{docstring}\n{snippet}"))
            materials.append(
                Material(
                    material_key=f"code:{rel}:{node.name}",
                    doc_id=rel,
                    section_id=node.name,
                    kind="code",
                    path=rel,
                    symbol=node.name,
                    version=1,
                    status="active",
                    title=f"{rel}::{node.name}",
                    body=snippet,
                    keywords=keywords,
                    tags=[f"symbol={node.name}", f"symbol_key={module}.{node.name}", f"module={module}", f"file={rel}"],
                    line_start=start,
                    line_end=end,
                    content_hash=content_hash(snippet),
                )
            )
    return materials


TEST_META_RE = re.compile(r"(?P<key>Covers|Role)\s*:\s*(?P<value>.+)")


def _test_metadata(docstring: str) -> tuple[list[str], str | None]:
    covers: list[str] = []
    role: str | None = None
    for match in TEST_META_RE.finditer(docstring):
        key = match.group("key")
        value = match.group("value").strip()
        if key == "Covers":
            covers.extend(part.strip() for part in value.split(",") if part.strip())
        elif key == "Role":
            role = value.split()[0].strip().lower()
    return covers, role


def _test_materials(root: Path) -> list[Material]:
    materials: list[Material] = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        tree = ast.parse(text)
        module = path.stem
        module_covers, module_role = _test_metadata(ast.get_docstring(tree) or "")
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            snippet = "\n".join(lines[start - 1 : end])
            docstring = ast.get_docstring(node) or ""
            local_covers, local_role = _test_metadata(docstring)
            covers = list(dict.fromkeys(module_covers + local_covers))
            role = local_role or module_role or "regression"
            tags = [f"test={node.name}", f"role={role}", f"module={module}", f"file={rel}"]
            tags.extend(f"covers={cover}" for cover in covers)
            materials.append(
                Material(
                    material_key=f"test:{rel}:{node.name}",
                    doc_id=rel,
                    section_id=node.name,
                    kind="test",
                    path=rel,
                    symbol=node.name,
                    version=1,
                    status="active",
                    title=f"{rel}::{node.name}",
                    body=snippet,
                    keywords=" ".join(tokens(f"{node.name}\n{docstring}\n{snippet}")),
                    tags=tags,
                    line_start=start,
                    line_end=end,
                    content_hash=content_hash(snippet),
                )
            )
    return materials


def collect_materials(root: Path = DEMO_APP) -> list[Material]:
    """收集 demo 工程里的规格、代码与测试。"""

    materials = _spec_materials(root) + _code_materials(root) + _test_materials(root)
    if not materials:
        raise RuntimeError(f"在 {root} 下没有找到可导入的工程资料")
    return materials


def import_materials(
    materials: list[Material],
    *,
    db_path: Path,
    evidence_path: Path | None = None,
) -> dict[str, Any]:
    imported_at = utc_now()
    with db.open_db(db_path) as connection:
        db.rebuild_schema(connection)
        for material in materials:
            db.insert_material(connection, material.to_record(imported_at))
        total = db.material_count(connection)
    digest = content_hash("".join(sorted(material.material_key for material in materials)))
    summary = {
        "imported_at": imported_at,
        "count": total,
        "specs": sum(1 for material in materials if material.kind == "spec"),
        "code": sum(1 for material in materials if material.kind == "code"),
        "tests": sum(1 for material in materials if material.kind == "test"),
        "digest": digest,
        "db_path": str(db_path),
        "materials": [
            {
                "key": material.material_key,
                "kind": material.kind,
                "path": material.path,
                "lines": [material.line_start, material.line_end],
                "version": material.version,
                "status": material.status,
            }
            for material in materials
        ],
    }
    if evidence_path is not None:
        write_json(evidence_path, summary)
    return summary
