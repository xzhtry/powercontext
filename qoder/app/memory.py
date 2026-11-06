"""PowerContext lifecycle and Memory client.

PowerContext is the durable research memory.  seekdb is the evidence library;
this module deliberately stores decisions, briefs and session handoffs rather
than duplicating paper rows.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import Settings

PREFIX = "RT_V1\n"


class MemoryUnavailable(RuntimeError):
    """PowerContext is down or returned an unexpected response."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _summary_for(kind: str, payload: dict[str, Any]) -> str:
    if kind == "research-brief":
        return f"研究问题：{payload.get('question', '')}"
    if kind == "evidence-decision":
        return f"{payload.get('stance_label', payload.get('stance', ''))} · {payload.get('title', '')}"
    if kind == "synthesis":
        return f"生成综述：{payload.get('title', '')}"
    if kind == "session-summary":
        return payload.get("summary", "一次研究会话的交接摘要")
    if kind == "next-action":
        return f"下一步：{payload.get('action', '')}"
    return payload.get("summary", kind)


class PowerContextServer:
    """Owns a loopback PowerContext Server backed by SQLite."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.process: subprocess.Popen | None = None
        self.started_here = False

    def _port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex(("127.0.0.1", self.settings.powercontext_port)) == 0

    def health(self) -> bool:
        try:
            response = httpx.get(
                f"{self.settings.powercontext_url}/health/ready", timeout=3
            )
            return response.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def _find_cli(self) -> Path | None:
        override = os.environ.get("RT_PC_BIN")
        if override and Path(override).exists():
            return Path(override)
        for name in ("powercontext.exe", "powercontext"):
            candidate = Path(sys.executable).parent / name
            if candidate.exists():
                return candidate
        found = shutil.which("powercontext")
        return Path(found) if found else None

    def _write_env(self) -> Path:
        home = self.settings.powercontext_home
        home.mkdir(parents=True, exist_ok=True)
        env_path = home / "powercontext.env"
        db_path = (home / "powercontext.db").as_posix()
        lines = [
            f"POWERCONTEXT_HOME={home.as_posix()}",
            "POWERCONTEXT_SERVER_DATABASE_KIND=sqlite",
            f"POWERCONTEXT_SERVER_DATABASE_URL=sqlite+aiosqlite:///{db_path}",
            "POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1",
            f"POWERCONTEXT_SERVER_HTTP_PORT={self.settings.powercontext_port}",
            "POWERCONTEXT_SERVER_ACCESS_MODE=disabled",
            "POWERCONTEXT_SERVER_MCP_ENABLED=false",
            "POWERCONTEXT_SERVER_DASHBOARD_ENABLED=false",
        ]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return env_path

    def start(self) -> None:
        if self.health():
            self.started_here = False
            return
        cli = self._find_cli()
        if not cli:
            raise MemoryUnavailable(
                "未找到 powercontext 命令。请安装 powercontext[cli,server]==1.4.1"
            )
        env_path = self._write_env()
        log_path = self.settings.powercontext_home / "server-launch.log"
        log = log_path.open("ab")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [str(cli), "server", "run", "--env-file", str(env_path)],
            cwd=str(self.settings.powercontext_home),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        self.started_here = True
        deadline = time.time() + 75
        while time.time() < deadline:
            if self.health():
                return
            if self.process.poll() is not None:
                break
            time.sleep(1)
        tail = ""
        with contextlib.suppress(Exception):
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2500:]
        raise MemoryUnavailable(f"PowerContext 启动失败。\n{tail}")

    def stop(self) -> None:
        if self.process and self.started_here:
            with contextlib.suppress(Exception):
                self.process.terminate()
            with contextlib.suppress(Exception):
                self.process.wait(timeout=10)
            self.process = None


class MemoryClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base = settings.powercontext_url
        self.timeout = 20
        self._scope_id: str | None = None

    # ------------------------------------------------------------------ scope
    def health(self) -> bool:
        try:
            return httpx.get(f"{self.base}/health/ready", timeout=3).status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def _read_scope_file(self) -> str | None:
        try:
            data = json.loads(self.settings.scope_file.read_text(encoding="utf-8"))
            return data.get("scope_id")
        except Exception:  # noqa: BLE001
            return None

    def reset_scope(self) -> None:
        """Forget the cached scope; the next call creates/loads a fresh one.

        Used by the UI's "reconnect" path after the local scope file or the
        PowerContext database has been reset independently.
        """

        self._scope_id = None
        with contextlib.suppress(FileNotFoundError):
            self.settings.scope_file.unlink()

    def ensure_scope(self) -> str:
        if self._scope_id:
            return self._scope_id
        existing = self._read_scope_file()
        if existing:
            self._scope_id = existing
            return existing
        try:
            response = httpx.post(
                f"{self.base}/v1/scopes",
                json={
                    "title": "研脉 ResearchThread",
                    "summary": "研究阅读、证据判断与综述记忆",
                    "idempotency_key": "researchthread-main",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            scope_id = response.json()["scope_id"]
        except Exception as error:  # noqa: BLE001
            raise MemoryUnavailable(f"无法创建 PowerContext Scope：{error}") from error
        self.settings.scope_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings.scope_file.write_text(
            json.dumps({"scope_id": scope_id, "created_at": utc_now()}, ensure_ascii=False),
            encoding="utf-8",
        )
        self._scope_id = scope_id
        return scope_id

    # ------------------------------------------------------------------ write
    def remember(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        summary: str | None = None,
    ) -> dict[str, Any]:
        scope_id = self.ensure_scope()
        record = {
            "schema": "researchthread.memory.v1",
            "kind": kind,
            "summary": summary or _summary_for(kind, payload),
            "session_id": payload.get("session_id", ""),
            "created_at": utc_now(),
            "payload": payload,
        }
        text = PREFIX + json.dumps(record, ensure_ascii=False, sort_keys=True)
        try:
            response = httpx.post(
                f"{self.base}/v1/memory/remember",
                json={
                    "scope_id": scope_id,
                    "kind": kind,
                    "text": text,
                    "reason": record["summary"][:200],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except Exception as error:  # noqa: BLE001
            raise MemoryUnavailable(f"写入 PowerContext 失败：{error}") from error
        artifact = {}
        records = body.get("records") or []
        if records:
            artifact = records[0].get("artifact") or {}
        record["artifact_id"] = artifact.get("artifact_id")
        record["revision"] = artifact.get("revision")
        return record

    # ------------------------------------------------------------------- read
    def entries(self, limit: int = 100) -> list[dict[str, Any]]:
        scope_id = self.ensure_scope()
        try:
            response = httpx.post(
                f"{self.base}/v1/memory/entries/list",
                json={"scope_id": scope_id, "limit": min(limit, 100)},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except Exception as error:  # noqa: BLE001
            raise MemoryUnavailable(f"读取 PowerContext 失败：{error}") from error
        parsed: list[dict[str, Any]] = []
        for entry in body.get("entries", []):
            text = entry.get("text", "")
            if not text.startswith(PREFIX):
                continue
            try:
                record = json.loads(text[len(PREFIX) :])
            except json.JSONDecodeError:
                continue
            artifact = entry.get("artifact") or {}
            parsed.append(
                {
                    "artifact_id": artifact.get("artifact_id"),
                    "revision": artifact.get("revision"),
                    "kind": entry.get("kind", record.get("kind", "unknown")),
                    "summary": record.get("summary", ""),
                    "session_id": record.get("session_id", ""),
                    "created_at": record.get("created_at", ""),
                    "payload": record.get("payload", {}),
                    "state": entry.get("state", "active"),
                }
            )
        parsed.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return parsed

    def state(self) -> dict[str, Any]:
        entries = self.entries()
        by_kind: dict[str, int] = {}
        for entry in entries:
            by_kind[entry["kind"]] = by_kind.get(entry["kind"], 0) + 1
        brief = next((entry for entry in entries if entry["kind"] == "research-brief"), None)
        last_session = next(
            (entry for entry in entries if entry["kind"] == "session-summary"), None
        )
        decisions = [entry for entry in entries if entry["kind"] == "evidence-decision"]
        return {
            "scope_id": self._scope_id,
            "total": len(entries),
            "by_kind": by_kind,
            "brief": brief["payload"] if brief else None,
            "brief_entry": brief,
            "last_session": last_session,
            "decisions": decisions,
            "entries": entries,
        }

    # --------------------------------------------------------------- shortcuts
    def record_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        return self.remember(
            "research-brief",
            brief,
            summary=f"研究问题：{brief.get('question', '')[:120]}",
        )

    def record_evidence(
        self,
        *,
        paper: dict[str, Any],
        stance: str,
        stance_label: str,
        note: str,
        session_id: str,
    ) -> dict[str, Any]:
        payload = {
            "session_id": session_id,
            "paper_id": paper["paper_id"],
            "arxiv_id": paper.get("arxiv_id", ""),
            "title": paper["title"],
            "year": paper.get("year"),
            "stance": stance,
            "stance_label": stance_label,
            "note": note,
        }
        return self.remember(
            "evidence-decision",
            payload,
            summary=f"{stance_label} · {paper['title'][:100]}",
        )

    def record_synthesis(
        self, *, title: str, synthesis_id: int, evidence_count: int, session_id: str
    ) -> dict[str, Any]:
        return self.remember(
            "synthesis",
            {
                "session_id": session_id,
                "synthesis_id": synthesis_id,
                "title": title,
                "evidence_count": evidence_count,
            },
            summary=f"生成综述：{title}",
        )

    def record_session(
        self,
        *,
        summary: str,
        searches: int,
        evidence_added: int,
        next_action: str,
        session_id: str,
    ) -> dict[str, Any]:
        return self.remember(
            "session-summary",
            {
                "session_id": session_id,
                "summary": summary,
                "searches": searches,
                "evidence_added": evidence_added,
                "next_action": next_action,
            },
            summary=summary,
        )
