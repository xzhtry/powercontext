"""研脉 ResearchThread — FastAPI application."""

from __future__ import annotations

import csv
import io
import json
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import synthesis
from .config import Settings, load_settings
from .memory import MemoryClient, MemoryUnavailable, PowerContextServer, utc_now
from .seekdb import STANCE_LABELS, STANCES, SeekdbRuntime


@dataclass
class Context:
    settings: Settings
    runtime: SeekdbRuntime
    pc_server: PowerContextServer
    memory: MemoryClient
    session_id: str
    memory_available: bool = False
    memory_error: str = ""
    searches: int = 0
    evidence_added: int = 0
    last_action: str = "打开研究台"
    brief: dict[str, Any] = field(default_factory=dict)

    def reload_brief(self) -> dict[str, Any]:
        if not self.memory_available:
            return self.brief
        try:
            state = self.memory.state()
            if state.get("brief"):
                self.brief = state["brief"]
        except MemoryUnavailable as error:
            self.memory_error = str(error)
        return self.brief


def _new_session_id() -> str:
    return "sess-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def _demo_payload(settings: Settings) -> dict[str, Any]:
    return json.loads((settings.data_dir / "demo.json").read_text(encoding="utf-8"))


def _try_start_memory(ctx: Context) -> None:
    if ctx.memory.health():
        ctx.memory_available = True
        ctx.memory_error = ""
        return
    if not ctx.settings.autostart:
        ctx.memory_available = False
        ctx.memory_error = "PowerContext 未运行（RT_AUTOSTART=0）"
        return
    try:
        ctx.pc_server.start()
    except Exception as error:  # noqa: BLE001
        ctx.memory_available = False
        ctx.memory_error = str(error)
        return
    ctx.memory_available = ctx.memory.health()
    ctx.memory_error = "" if ctx.memory_available else "PowerContext 健康检查失败"


def _seed_memory(ctx: Context) -> None:
    if not ctx.memory_available:
        return
    demo = _demo_payload(ctx.settings)
    try:
        state = ctx.memory.state()
    except MemoryUnavailable as error:
        ctx.memory_available = False
        ctx.memory_error = str(error)
        return
    if not state.get("brief"):
        brief = demo["brief"]
        brief["session_id"] = ctx.session_id
        try:
            ctx.memory.record_brief(brief)
        except MemoryUnavailable as error:
            ctx.memory_error = str(error)
    if not state.get("last_session"):
        try:
            ctx.memory.record_session(
                summary="示例研究项目已就绪：9 条证据已写入，下一步是补一条关于检索噪声的反方证据。",
                searches=0,
                evidence_added=0,
                next_action="补一条关于检索噪声的反方证据",
                session_id="seed",
            )
        except MemoryUnavailable as error:
            ctx.memory_error = str(error)
    # If seekdb already has the seeded evidence but Memory has no decisions,
    # mirror the evidence table into Memory once. This makes the memory timeline
    # useful from the very first run and is idempotent after that.
    if not state.get("decisions"):
        for row in ctx.runtime.list_evidence():
            try:
                ctx.memory.record_evidence(
                    paper=row,
                    stance=row["stance"],
                    stance_label=STANCE_LABELS.get(row["stance"], row["stance"]),
                    note=row["note"],
                    session_id="seed",
                )
            except MemoryUnavailable as error:
                ctx.memory_error = str(error)
                break


def _bootstrap_payload(ctx: Context) -> dict[str, Any]:
    stats = ctx.runtime.stats()
    memory_state: dict[str, Any] = {
        "available": ctx.memory_available,
        "error": ctx.memory_error,
        "scope_id": None,
        "total": 0,
        "by_kind": {},
        "last_session": None,
        "recovered": [],
    }
    brief = ctx.brief
    if ctx.memory_available:
        try:
            state = ctx.memory.state()
            if state.get("brief"):
                brief = state["brief"]
                ctx.brief = brief
            entries = state.get("entries", [])
            memory_state.update(
                {
                    "available": True,
                    "scope_id": state.get("scope_id"),
                    "total": state.get("total", len(entries)),
                    "by_kind": state.get("by_kind", {}),
                    "last_session": state.get("last_session"),
                    "recovered": entries[:8],
                }
            )
        except MemoryUnavailable as error:
            ctx.memory_available = False
            ctx.memory_error = str(error)
            memory_state["available"] = False
            memory_state["error"] = str(error)
    if not brief:
        brief = _demo_payload(ctx.settings)["brief"]
    health = {
        "seekdb": "ok" if ctx.runtime.health() else "down",
        "powercontext": "ok" if ctx.memory_available else "degraded",
        "papers": stats["papers"],
    }
    return {
        "app": {
            "name": "研脉",
            "name_en": "ResearchThread",
            "version": "0.1.0",
            "tagline": "把散落的论文，接成可复用的研究脉络。",
            "session_id": ctx.session_id,
        },
        "brief": brief,
        "stats": stats,
        "memory": memory_state,
        "activity": ctx.runtime.activity(10),
        "search_history": ctx.runtime.search_history(5),
        "latest_synthesis": (
            {
                key: value
                for key, value in (ctx.runtime.latest_synthesis() or {}).items()
                if key != "content"
            }
            or None
        ),
        "health": health,
    }


def _record_safely(ctx: Context, fn, *args, **kwargs) -> dict[str, Any] | None:
    if not ctx.memory_available:
        return None
    try:
        return fn(*args, **kwargs)
    except MemoryUnavailable as error:
        ctx.memory_available = False
        ctx.memory_error = str(error)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    settings.ensure_directories()
    runtime = SeekdbRuntime(settings)
    runtime.start()
    runtime.prepare_database()
    runtime.create_schema()
    runtime.seed_papers()
    runtime.seed_demo()
    ctx = Context(
        settings=settings,
        runtime=runtime,
        pc_server=PowerContextServer(settings),
        memory=MemoryClient(settings),
        session_id=_new_session_id(),
    )
    _try_start_memory(ctx)
    if ctx.memory_available:
        try:
            ctx.memory.ensure_scope()
        except MemoryUnavailable as error:
            ctx.memory_available = False
            ctx.memory_error = str(error)
    ctx.brief = _demo_payload(settings)["brief"]
    _seed_memory(ctx)
    ctx.reload_brief()
    app.state.ctx = ctx
    try:
        yield
    finally:
        ctx.pc_server.stop()
        runtime.stop()


app = FastAPI(title="研脉 ResearchThread", version="0.1.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=str(Path(__file__).parent / "static")), name="assets")


class BriefIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    scope: str = Field(default="", max_length=2000)
    criteria: list[str] = Field(default_factory=list, max_length=10)
    stage: str = Field(default="证据筛选", max_length=50)
    owner: str = Field(default="", max_length=100)
    next_action: str = Field(default="", max_length=500)


class EvidenceIn(BaseModel):
    paper_id: int
    stance: Literal["support", "challenge", "mixed"]
    note: str = Field(default="", max_length=4000)


class SynthesisIn(BaseModel):
    template: Literal["review", "weekly", "review_v2"] = "review"
    evidence_ids: list[int] | None = None


class SessionIn(BaseModel):
    next_action: str = Field(default="", max_length=500)


def get_ctx(request: Request) -> Context:
    return request.app.state.ctx


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html", media_type="text/html")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    ctx = get_ctx(request)
    return {
        "seekdb": ctx.runtime.health(),
        "powercontext": ctx.memory.health() if ctx.memory_available else False,
        "papers": ctx.runtime.count("papers"),
        "memory_available": ctx.memory_available,
        "memory_error": ctx.memory_error,
        "session_id": ctx.session_id,
    }


@app.get("/api/bootstrap")
def bootstrap(request: Request) -> dict[str, Any]:
    return _bootstrap_payload(get_ctx(request))


@app.post("/api/memory/reconnect")
def reconnect(request: Request) -> dict[str, Any]:
    ctx = get_ctx(request)
    _try_start_memory(ctx)
    if ctx.memory_available:
        try:
            # A previous run may have left a scope id from another database.
            # Reconnect means "re-resolve the scope", not just "retry HTTP".
            ctx.memory.reset_scope()
            ctx.memory.ensure_scope()
            _seed_memory(ctx)
            ctx.reload_brief()
        except MemoryUnavailable as error:
            ctx.memory_available = False
            ctx.memory_error = str(error)
    return _bootstrap_payload(ctx)


@app.get("/api/search")
def search(
    request: Request,
    q: str = Query(default="", max_length=300),
    year_from: int | None = None,
    year_to: int | None = None,
    topic: str | None = None,
    open_access: bool | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=1000),
) -> dict[str, Any]:
    ctx = get_ctx(request)
    result = ctx.runtime.search(
        q,
        year_from=year_from,
        year_to=year_to,
        topic=topic,
        open_access=open_access,
        limit=limit,
        offset=offset,
        session_id=ctx.session_id,
    )
    ctx.searches += 1
    ctx.last_action = f"检索「{q}」" if q else "浏览文献库"
    return result


@app.get("/api/papers/{paper_id}")
def paper_detail(request: Request, paper_id: int) -> dict[str, Any]:
    ctx = get_ctx(request)
    paper = ctx.runtime.paper(paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")
    return {"paper": paper, "evidence": ctx.runtime.evidence_for_paper(paper_id)}


@app.get("/api/evidence")
def evidence_list(request: Request, stance: str | None = None) -> dict[str, Any]:
    ctx = get_ctx(request)
    items = ctx.runtime.list_evidence(stance if stance in STANCES else None)
    counts = {key: 0 for key in STANCES}
    for item in ctx.runtime.list_evidence():
        counts[item["stance"]] = counts.get(item["stance"], 0) + 1
    return {"items": items, "counts": counts}


@app.post("/api/evidence")
def evidence_upsert(request: Request, body: EvidenceIn) -> dict[str, Any]:
    ctx = get_ctx(request)
    paper = ctx.runtime.paper(body.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="paper not found")
    note = body.note.strip()
    if not note:
        note = "（尚未填写判断，建议补一句为什么纳入/排除）"
    row = ctx.runtime.upsert_evidence(
        body.paper_id, body.stance, note, ctx.session_id
    )
    ctx.evidence_added += 1
    ctx.last_action = f"更新证据判断：{paper['title'][:60]}"
    ctx.runtime.log_activity(
        "evidence",
        f"{STANCE_LABELS[body.stance]} · {paper['title'][:90]}",
        {"paper_id": body.paper_id, "stance": body.stance},
    )
    memory_entry = _record_safely(
        ctx,
        ctx.memory.record_evidence,
        paper=paper,
        stance=body.stance,
        stance_label=STANCE_LABELS[body.stance],
        note=note,
        session_id=ctx.session_id,
    )
    return {"evidence": row, "memory": memory_entry, "memory_available": ctx.memory_available}


@app.delete("/api/evidence/{evidence_id}")
def evidence_delete(request: Request, evidence_id: int) -> dict[str, Any]:
    ctx = get_ctx(request)
    items = ctx.runtime.list_evidence()
    item = next((row for row in items if int(row["evidence_id"]) == evidence_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="evidence not found")
    ctx.runtime.delete_evidence(evidence_id)
    ctx.last_action = f"移除证据判断：{item['title'][:60]}"
    ctx.runtime.log_activity(
        "evidence-removed", f"移除 · {item['title'][:90]}", {"evidence_id": evidence_id}
    )
    memory_entry = _record_safely(
        ctx,
        ctx.memory.remember,
        "evidence-decision",
        {
            "session_id": ctx.session_id,
            "paper_id": item["paper_id"],
            "title": item["title"],
            "stance": "removed",
            "stance_label": "移除",
            "note": item.get("note", ""),
        },
        summary=f"移除证据 · {item['title'][:100]}",
    )
    return {"ok": True, "memory": memory_entry}


@app.post("/api/synthesis")
def synthesis_generate(request: Request, body: SynthesisIn) -> dict[str, Any]:
    ctx = get_ctx(request)
    all_evidence = ctx.runtime.list_evidence()
    if body.evidence_ids is None:
        selected = all_evidence
    else:
        wanted = set(body.evidence_ids)
        selected = [row for row in all_evidence if int(row["evidence_id"]) in wanted]
    if not selected:
        raise HTTPException(status_code=400, detail="请先选择至少一条证据")
    stance_order = {"support": 0, "challenge": 1, "mixed": 2}
    selected.sort(
        key=lambda row: (
            stance_order.get(row["stance"], 9),
            -int(row.get("year") or 0),
        )
    )
    brief = ctx.brief or _demo_payload(ctx.settings)["brief"]
    draft = synthesis.generate(brief, selected, body.template)
    saved = ctx.runtime.save_synthesis(
        draft["title"], draft["markdown"], [int(row["evidence_id"]) for row in selected], ctx.session_id
    )
    ctx.last_action = f"生成{draft['template_label']}：{draft['title'][:60]}"
    ctx.runtime.log_activity(
        "synthesis",
        f"{draft['template_label']} · {len(selected)} 条证据",
        {"synthesis_id": saved["synthesis_id"], "template": body.template},
    )
    memory_entry = _record_safely(
        ctx,
        ctx.memory.record_synthesis,
        title=draft["title"],
        synthesis_id=saved["synthesis_id"],
        evidence_count=len(selected),
        session_id=ctx.session_id,
    )
    return {
        **draft,
        "synthesis_id": saved["synthesis_id"],
        "created_at": saved["created_at"],
        "memory": memory_entry,
        "memory_available": ctx.memory_available,
    }


@app.get("/api/synthesis/latest")
def synthesis_latest(request: Request) -> dict[str, Any]:
    ctx = get_ctx(request)
    item = ctx.runtime.latest_synthesis()
    if not item:
        raise HTTPException(status_code=404, detail="no synthesis yet")
    return item


@app.post("/api/brief")
def brief_update(request: Request, body: BriefIn) -> dict[str, Any]:
    ctx = get_ctx(request)
    brief = body.model_dump()
    brief["updated_at"] = utc_now()
    brief["session_id"] = ctx.session_id
    ctx.brief = brief
    ctx.last_action = "更新研究问题"
    ctx.runtime.log_activity(
        "brief", f"更新研究问题：{body.question[:80]}", {"stage": body.stage}
    )
    memory_entry = _record_safely(ctx, ctx.memory.record_brief, brief)
    return {"brief": brief, "memory": memory_entry, "memory_available": ctx.memory_available}


@app.get("/api/memory")
def memory_detail(request: Request) -> dict[str, Any]:
    ctx = get_ctx(request)
    if not ctx.memory_available:
        return {
            "available": False,
            "error": ctx.memory_error,
            "scope_id": None,
            "entries": [],
            "by_kind": {},
        }
    try:
        state = ctx.memory.state()
    except MemoryUnavailable as error:
        ctx.memory_available = False
        ctx.memory_error = str(error)
        return {"available": False, "error": str(error), "scope_id": None, "entries": [], "by_kind": {}}
    return {
        "available": True,
        "scope_id": state.get("scope_id"),
        "total": state.get("total"),
        "by_kind": state.get("by_kind", {}),
        "entries": state.get("entries", []),
    }


@app.post("/api/session/new")
def session_new(request: Request, body: SessionIn | None = None) -> dict[str, Any]:
    ctx = get_ctx(request)
    next_action = (
        body.next_action
        if body and body.next_action
        else (ctx.brief.get("next_action") or "继续补证据，并记录检索条件")
    )
    summary = (
        f"本次会话检索 {ctx.searches} 次，新增 {ctx.evidence_added} 条证据判断；"
        f"最后动作：{ctx.last_action}。下一步：{next_action}。"
    )
    memory_entry = None
    if ctx.memory_available:
        memory_entry = _record_safely(
            ctx,
            ctx.memory.record_session,
            summary=summary,
            searches=ctx.searches,
            evidence_added=ctx.evidence_added,
            next_action=next_action,
            session_id=ctx.session_id,
        )
    old_session = ctx.session_id
    ctx.session_id = _new_session_id()
    ctx.searches = 0
    ctx.evidence_added = 0
    ctx.last_action = "开始新的研究会话"
    ctx.runtime.log_activity("session", summary, {"previous_session": old_session})
    payload = _bootstrap_payload(ctx)
    payload["handoff"] = {
        "previous_session": old_session,
        "summary": summary,
        "next_action": next_action,
        "memory": memory_entry,
    }
    return payload


@app.get("/api/export/evidence.md")
def export_evidence_md(request: Request) -> Response:
    ctx = get_ctx(request)
    items = ctx.runtime.list_evidence()
    lines = ["# 证据表", "", f"研究问题：{ctx.brief.get('question', '')}", ""]
    for item in items:
        lines.append(f"## [{item['stance_label']}] {item['title']}")
        lines.append("")
        lines.append(f"- 作者/年份：{item.get('authors', '')} ({item.get('year', '')})")
        lines.append(f"- 来源：{item.get('venue', '')} · {item.get('url', '')}")
        lines.append(f"- 判断：{item.get('note', '')}")
        lines.append("")
    return Response(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=researchthread-evidence.md"},
    )


@app.get("/api/export/evidence.csv")
def export_evidence_csv(request: Request) -> Response:
    ctx = get_ctx(request)
    items = ctx.runtime.list_evidence()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["title", "authors", "year", "venue", "stance", "note", "url", "arxiv_id"])
    for item in items:
        writer.writerow(
            [
                item.get("title", ""),
                item.get("authors", ""),
                item.get("year", ""),
                item.get("venue", ""),
                item.get("stance_label", ""),
                item.get("note", ""),
                item.get("url", ""),
                item.get("arxiv_id", ""),
            ]
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=researchthread-evidence.csv"},
    )


def _latex_escape(text: str) -> str:
    """Escape LaTeX special characters in a single pass to avoid double-escaping."""
    if not text:
        return ""
    _LATEX_MAP = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "_": "\\_",
        "#": "\\#",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    return "".join(_LATEX_MAP.get(ch, ch) for ch in text)


def _make_bibtex_key(item: dict[str, Any]) -> str:
    """Generate a unique BibTeX key from arxiv_id or authors+year."""
    arxiv_id = item.get("arxiv_id", "")
    if arxiv_id:
        return arxiv_id.replace("/", "_").replace(".", "_")
    authors = item.get("authors", "unknown")
    year = item.get("year", "nd")
    first_author = authors.split(",")[0].split(" and ")[0].split()[0] if authors else "unknown"
    return f"{first_author.lower()}{year}"


@app.get("/api/export/evidence.bib")
def export_evidence_bib(request: Request) -> Response:
    ctx = get_ctx(request)
    items = ctx.runtime.list_evidence()
    entries = []
    for item in items:
        key = _make_bibtex_key(item)
        title = _latex_escape(item.get("title", ""))
        author = _latex_escape(item.get("authors", ""))
        year = str(item.get("year", ""))
        journal = _latex_escape(item.get("venue", ""))
        url = item.get("url", "")
        note = _latex_escape(item.get("note", ""))
        stance_label = _latex_escape(item.get("stance_label", ""))

        entry_lines = [f"@article{{{key},"]
        entry_lines.append(f"  title = {{{title}}},")
        entry_lines.append(f"  author = {{{author}}},")
        if year:
            entry_lines.append(f"  year = {{{year}}},")
        if journal:
            entry_lines.append(f"  journal = {{{journal}}},")
        if url:
            entry_lines.append(f"  url = {{{url}}},")
        if note:
            full_note = f"[{stance_label}] {note}" if stance_label else note
            entry_lines.append(f"  note = {{{full_note}}},")
        entry_lines.append("}")
        entries.append("\n".join(entry_lines))

    content = "\n\n".join(entries) + "\n" if entries else ""
    return Response(
        content,
        media_type="application/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=researchthread-evidence.bib"},
    )


@app.exception_handler(MemoryUnavailable)
def memory_unavailable_handler(request: Request, exc: MemoryUnavailable):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc), "hint": "请启动 PowerContext，或点击记忆页的“重新连接”。"},
    )
