"""seekdb storage layer.

On Windows the native wheel ships ``seekdb.exe``.  The binding's in-process
``open()`` currently fails when the chosen port falls inside a Windows excluded
port range, so the app runs the shipped server on a free port and talks MySQL
to it.  On Linux/macOS the documented embedded binding is used directly.

All application SQL is MySQL-compatible and shared by both paths.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import Settings

STANCES = ("support", "challenge", "mixed")
STANCE_LABELS = {"support": "支持", "challenge": "挑战", "mixed": "混合"}

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS papers (
        paper_id INT AUTO_INCREMENT PRIMARY KEY,
        arxiv_id VARCHAR(64) NOT NULL,
        title VARCHAR(1024) NOT NULL,
        abstract TEXT NOT NULL,
        authors VARCHAR(1024) NOT NULL,
        pub_year INT NOT NULL,
        venue VARCHAR(255) NOT NULL,
        topic VARCHAR(64) NOT NULL,
        url VARCHAR(512) NOT NULL,
        doi VARCHAR(255) NOT NULL,
        open_access TINYINT NOT NULL DEFAULT 1,
        query_group VARCHAR(128) NOT NULL,
        imported_at VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_arxiv (arxiv_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence (
        evidence_id INT AUTO_INCREMENT PRIMARY KEY,
        paper_id INT NOT NULL,
        stance VARCHAR(16) NOT NULL,
        note TEXT NOT NULL,
        session_id VARCHAR(64) NOT NULL,
        created_at VARCHAR(40) NOT NULL,
        updated_at VARCHAR(40) NOT NULL,
        UNIQUE KEY uq_paper (paper_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS syntheses (
        synthesis_id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(512) NOT NULL,
        content TEXT NOT NULL,
        evidence_ids TEXT NOT NULL,
        session_id VARCHAR(64) NOT NULL,
        created_at VARCHAR(40) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_log (
        log_id INT AUTO_INCREMENT PRIMARY KEY,
        query TEXT NOT NULL,
        filters TEXT NOT NULL,
        result_count INT NOT NULL,
        elapsed_ms INT NOT NULL,
        top_ids TEXT NOT NULL,
        session_id VARCHAR(64) NOT NULL,
        created_at VARCHAR(40) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS activity (
        activity_id INT AUTO_INCREMENT PRIMARY KEY,
        kind VARCHAR(32) NOT NULL,
        summary VARCHAR(1024) NOT NULL,
        payload TEXT NOT NULL,
        created_at VARCHAR(40) NOT NULL
    )
    """,
]

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
    "could", "do", "does", "for", "from", "has", "have", "how", "if", "in",
    "into", "is", "it", "its", "may", "more", "most", "not", "of", "on", "or",
    "our", "than", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "to", "was", "we", "were", "what", "when", "which", "who",
    "will", "with", "would", "you", "your", "using", "use", "based", "via",
}

SYNONYMS = {
    "幻觉": "hallucination",
    "检索增强": "retrieval augmented generation",
    "检索": "retrieval",
    "增强": "augmented",
    "可靠性": "reliability",
    "可靠": "reliable",
    "事实性": "factuality",
    "引用": "citation",
    "长上下文": "long context",
    "评估": "evaluation",
    "评测": "benchmark evaluation",
    "生成": "generation",
    "知识": "knowledge",
    "证据": "evidence",
    "综述": "survey",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sql_literal(value: Any) -> str:
    """Quote a value for the SQL dialect used by seekdb.

    The embedded cursor has no parameter binding, so the application uses one
    escaping routine for both backends.  Values crossing this boundary are
    always application data (search text, notes, titles), never raw SQL.
    """

    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\x00", "").replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def _term_list(query: str) -> list[str]:
    lowered = query.lower()
    terms: list[str] = []
    for zh, en in SYNONYMS.items():
        if zh in lowered:
            terms.extend(en.split())
    words = re.findall(r"[a-z][a-z0-9\-]{2,}", lowered)
    terms.extend(words)
    # Also keep short acronyms such as RAG, LLM and GPT.
    terms.extend(re.findall(r"\b(?:[a-z]{2,3})\b", lowered))
    cleaned: list[str] = []
    for term in terms:
        term = term.strip("-")
        if not term or term in STOPWORDS:
            continue
        if len(term) < 2:
            continue
        if term not in cleaned:
            cleaned.append(term)
    return cleaned[:10]


def _snippet(text: str, terms: list[str], width: int = 280) -> str:
    lowered = text.lower()
    positions = [lowered.find(term) for term in terms if term and lowered.find(term) >= 0]
    if not positions:
        return text[:width] + ("…" if len(text) > width else "")
    position = min(positions)
    start = max(0, position - 70)
    end = min(len(text), start + width)
    fragment = text[start:end]
    if start:
        fragment = "…" + fragment
    if end < len(text):
        fragment += "…"
    return fragment


def _highlight(fragment: str, terms: list[str]) -> str:
    import html

    escaped = html.escape(fragment)
    for term in sorted({term for term in terms if len(term) >= 3}, key=len, reverse=True):
        escaped = re.sub(
            re.escape(html.escape(term)),
            lambda match: f"<mark>{match.group(0)}</mark>",
            escaped,
            flags=re.IGNORECASE,
        )
    return escaped


@dataclass
class SearchHit:
    paper_id: int
    arxiv_id: str
    title: str
    authors: str
    pub_year: int
    venue: str
    topic: str
    url: str
    doi: str
    open_access: int
    abstract: str
    fts_score: float
    score: float
    matched_terms: list[str]
    snippet: str

    def public(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "year": self.pub_year,
            "venue": self.venue,
            "topic": self.topic,
            "url": self.url,
            "doi": self.doi,
            "open_access": bool(self.open_access),
            "abstract": self.abstract,
            "score": round(self.score, 3),
            "fts_score": round(self.fts_score, 3),
            "matched_terms": self.matched_terms,
            "snippet_html": _highlight(self.snippet, self.matched_terms),
            "snippet": self.snippet,
        }


class SeekdbRuntime:
    """Owns the seekdb lifecycle and database connections."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.process: subprocess.Popen | None = None
        self.instance: Any = None
        self.started_here = False
        self._windows = sys.platform == "win32"

    # ---------------------------------------------------------------- lifecycle
    def _port_open(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    def _find_binary(self) -> Path | None:
        override = os.environ.get("RT_SEEKDB_BIN")
        if override and Path(override).exists():
            return Path(override)
        candidates: list[Path] = []
        try:
            import importlib.util

            spec = importlib.util.find_spec("pylibseekdb")
            if spec and spec.origin:
                package_dir = Path(spec.origin).parent
                candidates.append(package_dir.parent / "pylibseekdb.libs" / "seekdb.exe")
                candidates.append(package_dir.parent / "pylibseekdb.libs" / "seekdb")
        except Exception:  # noqa: BLE001
            pass
        candidates.extend(
            [
                Path(sys.prefix) / "Lib" / "site-packages" / "pylibseekdb.libs" / "seekdb.exe",
                Path(sys.prefix) / "lib" / "site-packages" / "pylibseekdb.libs" / "seekdb",
            ]
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        found = shutil.which("seekdb")
        return Path(found) if found else None

    def _check_existing(self) -> bool:
        if not self._windows:
            return False
        if not self._port_open(self.settings.seekdb_port):
            return False
        try:
            conn = self._connect_raw(self.settings.seekdb_port, "test")
            conn.close()
            return True
        except Exception:  # noqa: BLE001
            return False

    def start(self) -> None:
        if self._check_existing():
            self.started_here = False
            return
        if not self._windows:
            self._start_embedded()
            return
        self.settings.ensure_directories()
        binary = self._find_binary()
        if not binary:
            raise RuntimeError(
                "未找到 seekdb 可执行文件。请先安装 pylibseekdb："
                "pip install pylibseekdb==1.4.0.post2"
            )
        log_path = self.settings.seekdb_base / "log" / "server-launch.log"
        log = log_path.open("ab")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        args = [
            str(binary),
            "--nodaemon",
            "--base-dir",
            str(self.settings.seekdb_base),
            "--data-dir",
            str(self.settings.seekdb_store),
            "--port",
            str(self.settings.seekdb_port),
            "--log-level",
            "WARN",
            "--parameter",
            "datafile_size=2G",
            "--parameter",
            "datafile_maxsize=4G",
            "--parameter",
            "log_disk_size=2G",
        ]
        self.process = subprocess.Popen(
            args,
            cwd=str(self.settings.seekdb_base),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        self.started_here = True
        deadline = time.time() + 90
        last_error = ""
        while time.time() < deadline:
            if self._port_open(self.settings.seekdb_port):
                try:
                    conn = self._connect_raw(self.settings.seekdb_port, "test")
                    conn.close()
                    return
                except Exception as error:  # noqa: BLE001
                    last_error = str(error)
            if self.process.poll() is not None:
                break
            time.sleep(1)
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            f"seekdb 启动失败（端口 {self.settings.seekdb_port}）。{last_error}\n{tail}"
        )

    def _start_embedded(self) -> None:
        import pylibseekdb as seekdb  # type: ignore

        db_dir = self.settings.runtime / "seekdb-embedded"
        db_dir.mkdir(parents=True, exist_ok=True)
        self.instance = seekdb.open(str(db_dir))
        self.started_here = True

    def stop(self) -> None:
        if self.process and self.started_here:
            with contextlib.suppress(Exception):
                self.process.terminate()
            with contextlib.suppress(Exception):
                self.process.wait(timeout=10)
            self.process = None
        if self.instance is not None:
            with contextlib.suppress(Exception):
                self.instance.close()
            self.instance = None

    # -------------------------------------------------------------- connections
    def _connect_raw(self, port: int, database: str):
        import pymysql

        return pymysql.connect(
            host="127.0.0.1",
            port=port,
            user=os.environ.get("RT_SEEKDB_USER", "root"),
            password=os.environ.get("RT_SEEKDB_PASSWORD", ""),
            database=database,
            charset="utf8mb4",
            autocommit=True,
            connect_timeout=8,
            read_timeout=30,
            write_timeout=30,
        )

    def connect(self, database: str = "researchthread"):
        if self._windows:
            return self._connect_raw(self.settings.seekdb_port, database)
        import pylibseekdb as seekdb  # type: ignore

        return seekdb.connect(database=database, autocommit=True)

    @contextlib.contextmanager
    def cursor(self, database: str = "researchthread") -> Iterator[Any]:
        conn = self.connect(database)
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            with contextlib.suppress(Exception):
                cursor.close()
            with contextlib.suppress(Exception):
                conn.close()

    def execute(self, sql: str, database: str = "researchthread") -> None:
        with self.cursor(database) as cursor:
            cursor.execute(sql)

    def fetch(self, sql: str, columns: list[str], database: str = "researchthread") -> list[dict[str, Any]]:
        with self.cursor(database) as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def fetchone(self, sql: str, database: str = "researchthread"):
        with self.cursor(database) as cursor:
            cursor.execute(sql)
            return cursor.fetchone()

    # ------------------------------------------------------------------- schema
    def prepare_database(self) -> None:
        if self._windows:
            test_conn = self._connect_raw(self.settings.seekdb_port, "test")
            try:
                with test_conn.cursor() as cur:
                    cur.execute("CREATE DATABASE IF NOT EXISTS researchthread")
            finally:
                test_conn.close()
            return
        # Embedded connections need a database that already exists.
        import pylibseekdb as seekdb  # type: ignore

        conn = seekdb.connect(database="test", autocommit=True)
        try:
            cursor = conn.cursor()
            cursor.execute("CREATE DATABASE IF NOT EXISTS researchthread")
            cursor.close()
        finally:
            conn.close()

    def create_schema(self) -> None:
        with self.cursor() as cursor:
            for statement in SCHEMA:
                cursor.execute(statement)
            cursor.execute("SHOW INDEX FROM papers")
            indexes = {row[2] for row in cursor.fetchall()}
            if "ft_papers" not in indexes:
                cursor.execute(
                    "CREATE FULLTEXT INDEX ft_papers ON papers(title, abstract) WITH PARSER ngram"
                )

    def count(self, table: str) -> int:
        row = self.fetchone(f"SELECT COUNT(*) FROM {table}")
        return int(row[0]) if row else 0

    # --------------------------------------------------------------------- seed
    def seed_papers(self) -> int:
        if self.count("papers") > 0:
            return 0
        payload = json.loads((self.settings.data_dir / "papers.json").read_text(encoding="utf-8"))
        papers = payload["papers"]
        imported_at = utc_now()
        rows = [
            (
                paper["arxiv_id"],
                paper["title"],
                paper["abstract"],
                paper.get("authors", ""),
                int(paper.get("year", 0)),
                paper.get("venue", "arXiv 预印本"),
                paper.get("topic", "交叉学科"),
                paper.get("url", ""),
                paper.get("doi", ""),
                1 if paper.get("open_access") else 0,
                paper.get("query_group", ""),
                imported_at,
            )
            for paper in papers
        ]
        columns = (
            "arxiv_id, title, abstract, authors, pub_year, venue, topic, url, doi, "
            "open_access, query_group, imported_at"
        )
        with self.cursor() as cursor:
            for start in range(0, len(rows), 25):
                chunk = rows[start : start + 25]
                values = ", ".join(
                    "(" + ", ".join(sql_literal(value) for value in row) + ")" for row in chunk
                )
                cursor.execute(f"INSERT IGNORE INTO papers ({columns}) VALUES {values}")
        self.log_activity(
            "seed", f"导入 {len(rows)} 篇 arXiv 文献到 seekdb", {"papers": len(rows)}
        )
        return len(rows)

    def seed_demo(self) -> int:
        if not self.settings.seed_demo or self.count("evidence") > 0:
            return 0
        demo = json.loads((self.settings.data_dir / "demo.json").read_text(encoding="utf-8"))
        added = 0
        with self.cursor() as cursor:
            for item in demo.get("evidence", []):
                cursor.execute(
                    f"SELECT paper_id FROM papers WHERE arxiv_id = {sql_literal(item['arxiv_id'])}"
                )
                row = cursor.fetchone()
                if not row:
                    continue
                paper_id = int(row[0])
                now = utc_now()
                cursor.execute(
                    "INSERT INTO evidence (paper_id, stance, note, session_id, created_at, updated_at) "
                    f"VALUES ({paper_id}, {sql_literal(item['stance'])}, {sql_literal(item['note'])}, "
                    f"'seed', {sql_literal(now)}, {sql_literal(now)})"
                )
                added += 1
        if added:
            self.log_activity(
                "seed", f"写入 {added} 条示例证据判断", {"evidence": added}
            )
        return added

    # ------------------------------------------------------------------- search
    def search(
        self,
        query: str,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        topic: str | None = None,
        open_access: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        session_id: str = "",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        terms = _term_list(query)
        filters: list[str] = []
        if year_from:
            filters.append(f"pub_year >= {int(year_from)}")
        if year_to:
            filters.append(f"pub_year <= {int(year_to)}")
        if topic:
            filters.append(f"topic = {sql_literal(topic)}")
        if open_access is True:
            filters.append("open_access = 1")
        where_extra = (" AND " + " AND ".join(filters)) if filters else ""
        base_columns = (
            "paper_id, arxiv_id, title, authors, pub_year, venue, topic, url, doi, "
            "open_access, abstract"
        )
        rows: list[tuple] = []
        used_fts = False
        if terms:
            fts_query = " ".join(terms)
            sql = (
                f"SELECT {base_columns}, MATCH(title, abstract) AGAINST ({sql_literal(fts_query)}) AS fts_score "
                "FROM papers WHERE MATCH(title, abstract) AGAINST "
                f"({sql_literal(fts_query)}){where_extra} "
                "ORDER BY fts_score DESC, pub_year DESC LIMIT 160"
            )
            try:
                with self.cursor() as cursor:
                    cursor.execute(sql)
                    rows = list(cursor.fetchall())
                used_fts = True
            except Exception:  # noqa: BLE001 - retry with LIKE
                rows = []
        if not rows:
            like_parts = []
            for term in terms[:4] or [query.strip().lower()]:
                if not term:
                    continue
                like_parts.append(f"title LIKE {sql_literal('%' + term + '%')}")
                like_parts.append(f"abstract LIKE {sql_literal('%' + term + '%')}")
            like_where = " OR ".join(like_parts) if like_parts else "1 = 1"
            sql = (
                f"SELECT {base_columns}, 1.0 AS fts_score FROM papers "
                f"WHERE ({like_where}){where_extra} ORDER BY pub_year DESC LIMIT 160"
            )
            with self.cursor() as cursor:
                cursor.execute(sql)
                rows = list(cursor.fetchall())
        hits: list[SearchHit] = []
        if not terms:
            min_hits = 0
        elif len(terms) <= 2:
            min_hits = len(terms)
        else:
            min_hits = max(2, len(terms) - 2)
        for row in rows:
            paper_id, arxiv_id, title, authors, year, venue, paper_topic, url, doi, oa, abstract, fts_score = row
            haystack = f"{title} {abstract}".lower()
            matched = [term for term in terms if term in haystack]
            if terms and len(matched) < min_hits:
                continue
            title_hits = sum(1 for term in matched if term in title.lower())
            score = float(fts_score or 0.0) + 0.35 * len(matched) + 0.6 * title_hits
            hits.append(
                SearchHit(
                    paper_id=int(paper_id),
                    arxiv_id=str(arxiv_id),
                    title=str(title),
                    authors=str(authors),
                    pub_year=int(year),
                    venue=str(venue),
                    topic=str(paper_topic),
                    url=str(url),
                    doi=str(doi),
                    open_access=int(oa),
                    abstract=str(abstract),
                    fts_score=float(fts_score or 0.0),
                    score=score,
                    matched_terms=matched,
                    snippet=_snippet(str(abstract), terms),
                )
            )
        hits.sort(key=lambda hit: (-hit.score, -hit.pub_year, hit.title))
        total = len(hits)
        page = hits[offset : offset + limit]
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        self.log_search(query, filters, total, elapsed_ms, [hit.paper_id for hit in page], session_id)
        return {
            "query": query,
            "terms": terms,
            "total": total,
            "limit": limit,
            "offset": offset,
            "elapsed_ms": elapsed_ms,
            "mode": "seekdb FULLTEXT ngram + lexical verification" if used_fts else "seekdb LIKE fallback",
            "results": [hit.public() for hit in page],
            "sql_trace": {
                "engine": "seekdb",
                "statement": sql if terms else "recent papers",
                "candidates": len(rows),
                "verified": total,
            },
        }

    def log_search(
        self,
        query: str,
        filters: list[str],
        result_count: int,
        elapsed_ms: int,
        top_ids: list[int],
        session_id: str,
    ) -> None:
        with contextlib.suppress(Exception):
            self.execute(
                "INSERT INTO search_log (query, filters, result_count, elapsed_ms, top_ids, session_id, created_at) "
                f"VALUES ({sql_literal(query)}, {sql_literal(json.dumps(filters, ensure_ascii=False))}, "
                f"{int(result_count)}, {int(elapsed_ms)}, {sql_literal(','.join(map(str, top_ids)))}, "
                f"{sql_literal(session_id)}, {sql_literal(utc_now())})"
            )

    # ----------------------------------------------------------------- evidence
    def paper(self, paper_id: int) -> dict[str, Any] | None:
        rows = self.fetch(
            "SELECT paper_id, arxiv_id, title, authors, pub_year, venue, topic, url, doi, "
            "open_access, abstract FROM papers "
            f"WHERE paper_id = {int(paper_id)}",
            [
                "paper_id", "arxiv_id", "title", "authors", "year", "venue", "topic",
                "url", "doi", "open_access", "abstract",
            ],
        )
        if not rows:
            return None
        item = rows[0]
        item["open_access"] = bool(item["open_access"])
        return item

    def evidence_for_paper(self, paper_id: int) -> dict[str, Any] | None:
        rows = self.fetch(
            "SELECT evidence_id, paper_id, stance, note, session_id, created_at, updated_at "
            f"FROM evidence WHERE paper_id = {int(paper_id)}",
            ["evidence_id", "paper_id", "stance", "note", "session_id", "created_at", "updated_at"],
        )
        return rows[0] if rows else None

    def upsert_evidence(
        self, paper_id: int, stance: str, note: str, session_id: str
    ) -> dict[str, Any]:
        if stance not in STANCES:
            raise ValueError(f"invalid stance: {stance}")
        existing = self.evidence_for_paper(paper_id)
        now = utc_now()
        with self.cursor() as cursor:
            if existing:
                cursor.execute(
                    "UPDATE evidence SET "
                    f"stance = {sql_literal(stance)}, note = {sql_literal(note)}, "
                    f"session_id = {sql_literal(session_id)}, updated_at = {sql_literal(now)} "
                    f"WHERE evidence_id = {int(existing['evidence_id'])}"
                )
            else:
                cursor.execute(
                    "INSERT INTO evidence (paper_id, stance, note, session_id, created_at, updated_at) "
                    f"VALUES ({int(paper_id)}, {sql_literal(stance)}, {sql_literal(note)}, "
                    f"{sql_literal(session_id)}, {sql_literal(now)}, {sql_literal(now)})"
                )
        return self.evidence_for_paper(paper_id) or {}

    def delete_evidence(self, evidence_id: int) -> None:
        self.execute(f"DELETE FROM evidence WHERE evidence_id = {int(evidence_id)}")

    def list_evidence(self, stance: str | None = None) -> list[dict[str, Any]]:
        where = f"WHERE e.stance = {sql_literal(stance)}" if stance in STANCES else ""
        rows = self.fetch(
            "SELECT e.evidence_id, e.paper_id, e.stance, e.note, e.session_id, "
            "e.created_at, e.updated_at, p.title, p.authors, p.pub_year, p.venue, "
            "p.topic, p.url, p.arxiv_id, p.abstract "
            "FROM evidence e JOIN papers p ON p.paper_id = e.paper_id "
            f"{where} ORDER BY e.updated_at DESC, e.evidence_id DESC",
            [
                "evidence_id", "paper_id", "stance", "note", "session_id", "created_at",
                "updated_at", "title", "authors", "year", "venue", "topic", "url",
                "arxiv_id", "abstract",
            ],
        )
        for item in rows:
            item["stance_label"] = STANCE_LABELS.get(item["stance"], item["stance"])
        return rows

    # --------------------------------------------------------------- synthesis
    def save_synthesis(
        self, title: str, content: str, evidence_ids: list[int], session_id: str
    ) -> dict[str, Any]:
        now = utc_now()
        with self.cursor() as cursor:
            cursor.execute(
                "INSERT INTO syntheses (title, content, evidence_ids, session_id, created_at) "
                f"VALUES ({sql_literal(title)}, {sql_literal(content)}, "
                f"{sql_literal(','.join(map(str, evidence_ids)))}, {sql_literal(session_id)}, "
                f"{sql_literal(now)})"
            )
            cursor.execute("SELECT LAST_INSERT_ID()")
            row = cursor.fetchone()
        synthesis_id = int(row[0]) if row else 0
        return {
            "synthesis_id": synthesis_id,
            "title": title,
            "content": content,
            "evidence_ids": evidence_ids,
            "created_at": now,
        }

    def latest_synthesis(self) -> dict[str, Any] | None:
        rows = self.fetch(
            "SELECT synthesis_id, title, content, evidence_ids, session_id, created_at "
            "FROM syntheses ORDER BY synthesis_id DESC LIMIT 1",
            ["synthesis_id", "title", "content", "evidence_ids", "session_id", "created_at"],
        )
        return rows[0] if rows else None

    # ----------------------------------------------------------------- activity
    def log_activity(self, kind: str, summary: str, payload: dict[str, Any] | None = None) -> None:
        with contextlib.suppress(Exception):
            self.execute(
                "INSERT INTO activity (kind, summary, payload, created_at) "
                f"VALUES ({sql_literal(kind)}, {sql_literal(summary)}, "
                f"{sql_literal(json.dumps(payload or {}, ensure_ascii=False))}, {sql_literal(utc_now())})"
            )

    def activity(self, limit: int = 12) -> list[dict[str, Any]]:
        rows = self.fetch(
            "SELECT kind, summary, payload, created_at FROM activity "
            f"ORDER BY activity_id DESC LIMIT {int(limit)}",
            ["kind", "summary", "payload", "created_at"],
        )
        for item in rows:
            with contextlib.suppress(Exception):
                item["payload"] = json.loads(item["payload"])
        return rows

    def stats(self) -> dict[str, Any]:
        papers = self.count("papers")
        evidence = self.count("evidence")
        stance_rows = self.fetch(
            "SELECT stance, COUNT(*) FROM evidence GROUP BY stance",
            ["stance", "count"],
        )
        stances = {row["stance"]: int(row["count"]) for row in stance_rows}
        topic_rows = self.fetch(
            "SELECT topic, COUNT(*) AS count FROM papers GROUP BY topic ORDER BY count DESC LIMIT 6",
            ["topic", "count"],
        )
        years = self.fetchone("SELECT MIN(pub_year), MAX(pub_year) FROM papers") or (0, 0)
        searches = self.count("search_log")
        syntheses = self.count("syntheses")
        return {
            "papers": papers,
            "evidence": evidence,
            "stances": {stance: stances.get(stance, 0) for stance in STANCES},
            "topics": [{"topic": row["topic"], "count": int(row["count"])} for row in topic_rows],
            "year_min": int(years[0] or 0),
            "year_max": int(years[1] or 0),
            "searches": searches,
            "syntheses": syntheses,
        }

    def search_history(self, limit: int = 6) -> list[dict[str, Any]]:
        return self.fetch(
            "SELECT query, result_count, elapsed_ms, created_at FROM search_log "
            f"ORDER BY log_id DESC LIMIT {int(limit)}",
            ["query", "result_count", "elapsed_ms", "created_at"],
        )

    def health(self) -> bool:
        try:
            row = self.fetchone("SELECT 1")
            return bool(row and row[0] == 1)
        except Exception:  # noqa: BLE001
            return False
