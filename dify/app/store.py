"""seekdb 存储层。

分工：
- ``inn_cards``：客栈世界设定、道具、NPC、传闻与事件卡；提供 ngram 全文检索。
- ``inn_plans``：每个回合的判定快照，保证“先判定、后叙述、再落账”。
- ``inn_ledger``：真实发生过的操作流水，供复盘和评审核对。

PowerContext 只保存玩家状态与剧情记忆；seekdb 只保存世界资料和回合流水。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pylibseekdb as seekdb

from app.config import CARDS_FILE


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def q(value: Any) -> str:
    """把值转成安全的 SQL 字面量（seekdb 驱动使用 MySQL 风格转义）。"""

    text = str(value)
    return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS inn_cards (
        card_id VARCHAR(64) PRIMARY KEY,
        kind VARCHAR(16) NOT NULL,
        title VARCHAR(200) NOT NULL,
        body TEXT NOT NULL,
        tags TEXT NOT NULL,
        keywords TEXT NOT NULL,
        effect_json TEXT NOT NULL,
        weight INT NOT NULL,
        status VARCHAR(16) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inn_plans (
        plan_id VARCHAR(64) PRIMARY KEY,
        player_id VARCHAR(64) NOT NULL,
        generation INT NOT NULL,
        turn INT NOT NULL,
        action TEXT NOT NULL,
        intent VARCHAR(24) NOT NULL,
        target VARCHAR(64) NOT NULL,
        plan_json TEXT NOT NULL,
        committed INT NOT NULL,
        reply_markdown TEXT NOT NULL,
        created_at VARCHAR(40) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inn_ledger (
        ledger_id VARCHAR(64) PRIMARY KEY,
        player_id VARCHAR(64) NOT NULL,
        generation INT NOT NULL,
        turn INT NOT NULL,
        action TEXT NOT NULL,
        intent VARCHAR(24) NOT NULL,
        target VARCHAR(64) NOT NULL,
        card_ids TEXT NOT NULL,
        deltas_json TEXT NOT NULL,
        narrative TEXT NOT NULL,
        created_at VARCHAR(40) NOT NULL
    )
    """,
]


class Store:
    def __init__(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.path = path
        seekdb.open(str(path))
        self.connection = seekdb.connect()
        self.lock = threading.RLock()
        self._init_schema()
        self._seed_cards()

    def _reconnect(self) -> None:
        """嵌入式 seekdb 的空闲连接可能被回收；重连，必要时重启内嵌实例。"""

        with self.lock:
            try:
                self.connection.close()
            except Exception:
                pass
            try:
                self.connection = seekdb.connect()
                self.connection.cursor().execute("SELECT 1")
                return
            except Exception:
                pass
            try:
                seekdb.close()
            except Exception:
                pass
            seekdb.open(str(self.path))
            self.connection = seekdb.connect()

    def ensure_alive(self) -> None:
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchall()
        except Exception:
            self._reconnect()

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    def _cursor(self):
        return self.connection.cursor()

    def _execute(self, sql: str) -> list[tuple]:
        with self.lock:
            cursor = self._cursor()
            cursor.execute(sql)
            try:
                return list(cursor.fetchall())
            except Exception:
                return []

    def _commit(self) -> None:
        with self.lock:
            self.connection.commit()

    def _init_schema(self) -> None:
        with self.lock:
            cursor = self._cursor()
            for statement in SCHEMA:
                cursor.execute(statement)
            self.connection.commit()
            try:
                cursor.execute("SHOW INDEX FROM inn_cards")
                indexes = {str(row[2]) for row in cursor.fetchall()}
            except Exception:
                indexes = set()
            if "ft_inn_cards" not in indexes:
                cursor.execute(
                    "CREATE FULLTEXT INDEX ft_inn_cards ON inn_cards(title, body, keywords) "
                    "WITH PARSER ngram"
                )
                self.connection.commit()

    def _seed_cards(self) -> None:
        rows = self._execute("SELECT COUNT(*) FROM inn_cards")
        if rows and int(rows[0][0]) > 0:
            return
        cards = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
        with self.lock:
            cursor = self._cursor()
            for card in cards:
                cursor.execute(
                    "INSERT INTO inn_cards "
                    "(card_id, kind, title, body, tags, keywords, effect_json, weight, status) "
                    f"VALUES ({q(card['card_id'])}, {q(card['kind'])}, {q(card['title'])}, "
                    f"{q(card['body'])}, {q(card['tags'])}, {q(card['keywords'])}, "
                    f"{q(json.dumps(card.get('effect', {}), ensure_ascii=False))}, "
                    f"{int(card.get('weight', 1))}, 'active')"
                )
            self.connection.commit()

    def close(self) -> None:
        with self.lock:
            try:
                self.connection.close()
            finally:
                try:
                    seekdb.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 世界卡检索
    # ------------------------------------------------------------------
    def search_cards(self, query: str, *, tags: list[str] | None = None, limit: int = 6) -> list[dict[str, Any]]:
        query = " ".join(str(query).split())[:400]
        tags = [tag for tag in (tags or []) if tag][:8]
        with self.lock:
            cursor = self._cursor()
            rows: list[tuple] = []
            if query:
                literal = q(query)
                try:
                    cursor.execute(
                        "SELECT card_id, kind, title, body, tags, keywords, effect_json, weight, "
                        f"MATCH(title, body, keywords) AGAINST ({literal}) AS score "
                        "FROM inn_cards WHERE status='active' "
                        f"AND MATCH(title, body, keywords) AGAINST ({literal}) "
                        "ORDER BY score DESC, weight DESC LIMIT "
                        f"{max(1, min(int(limit), 20))}"
                    )
                    rows = list(cursor.fetchall())
                except Exception:
                    rows = []
            if not rows and tags:
                likes = " OR ".join(f"tags LIKE {q('%' + tag + '%')}" for tag in tags)
                cursor.execute(
                    "SELECT card_id, kind, title, body, tags, keywords, effect_json, weight, 0.0 AS score "
                    f"FROM inn_cards WHERE status='active' AND ({likes}) "
                    f"ORDER BY weight DESC LIMIT {max(1, min(int(limit), 20))}"
                )
                rows = list(cursor.fetchall())
            if not rows:
                cursor.execute(
                    "SELECT card_id, kind, title, body, tags, keywords, effect_json, weight, 0.0 AS score "
                    "FROM inn_cards WHERE status='active' ORDER BY weight DESC, card_id LIMIT "
                    f"{max(1, min(int(limit), 20))}"
                )
                rows = list(cursor.fetchall())
        columns = ("card_id", "kind", "title", "body", "tags", "keywords", "effect_json", "weight", "score")
        cards = []
        for row in rows:
            item = dict(zip(columns, row, strict=True))
            try:
                item["effect"] = json.loads(item.pop("effect_json"))
            except Exception:
                item["effect"] = {}
                item.pop("effect_json", None)
            item["score"] = round(float(item.get("score", 0.0)), 4)
            cards.append(item)
        return cards

    def card_count(self) -> int:
        rows = self._execute("SELECT COUNT(*) FROM inn_cards")
        return int(rows[0][0]) if rows else 0

    def card_kinds(self) -> dict[str, int]:
        rows = self._execute("SELECT kind, COUNT(*) FROM inn_cards GROUP BY kind ORDER BY kind")
        return {str(kind): int(count) for kind, count in rows}

    # ------------------------------------------------------------------
    # 回合判定快照
    # ------------------------------------------------------------------
    def save_plan(self, player_id: str, plan: dict[str, Any]) -> str:
        plan_id = f"plan-{uuid4().hex[:16]}"
        plan["plan_id"] = plan_id
        now = utc_now()
        with self.lock:
            cursor = self._cursor()
            cursor.execute(
                "INSERT INTO inn_plans "
                "(plan_id, player_id, generation, turn, action, intent, target, plan_json, "
                "committed, reply_markdown, created_at) VALUES "
                f"({q(plan_id)}, {q(player_id)}, {int(plan['generation'])}, {int(plan['turn'])}, "
                f"{q(plan['action'])}, {q(plan['intent'])}, {q(plan['target'])}, "
                f"{q(json.dumps(plan, ensure_ascii=False))}, 0, '', {q(now)})"
            )
            self.connection.commit()
        return plan_id

    def latest_open_plan(self, player_id: str) -> dict[str, Any] | None:
        with self.lock:
            cursor = self._cursor()
            cursor.execute(
                "SELECT plan_json FROM inn_plans "
                f"WHERE player_id={q(player_id)} AND committed=0 "
                "ORDER BY created_at DESC LIMIT 1"
            )
            rows = list(cursor.fetchall())
        if not rows:
            return None
        try:
            return json.loads(rows[0][0])
        except Exception:
            return None

    def latest_plan(self, player_id: str) -> dict[str, Any] | None:
        with self.lock:
            cursor = self._cursor()
            cursor.execute(
                "SELECT plan_json, committed, reply_markdown FROM inn_plans "
                f"WHERE player_id={q(player_id)} ORDER BY created_at DESC LIMIT 1"
            )
            rows = list(cursor.fetchall())
        if not rows:
            return None
        try:
            plan = json.loads(rows[0][0])
        except Exception:
            return None
        plan["committed"] = bool(rows[0][1])
        plan["reply_markdown"] = rows[0][2]
        return plan

    def mark_plan_committed(self, plan_id: str, reply_markdown: str) -> None:
        with self.lock:
            cursor = self._cursor()
            cursor.execute(
                "UPDATE inn_plans SET committed=1, "
                f"reply_markdown={q(reply_markdown)} WHERE plan_id={q(plan_id)}"
            )
            self.connection.commit()

    def drop_open_plans(self, player_id: str) -> None:
        with self.lock:
            cursor = self._cursor()
            cursor.execute(f"DELETE FROM inn_plans WHERE player_id={q(player_id)} AND committed=0")
            self.connection.commit()

    # ------------------------------------------------------------------
    # 流水
    # ------------------------------------------------------------------
    def add_ledger(
        self,
        *,
        player_id: str,
        generation: int,
        turn: int,
        action: str,
        intent: str,
        target: str,
        card_ids: list[str],
        deltas: dict[str, Any],
        narrative: str,
    ) -> str:
        ledger_id = f"ledger-{uuid4().hex[:16]}"
        with self.lock:
            cursor = self._cursor()
            cursor.execute(
                "INSERT INTO inn_ledger "
                "(ledger_id, player_id, generation, turn, action, intent, target, card_ids, "
                "deltas_json, narrative, created_at) VALUES "
                f"({q(ledger_id)}, {q(player_id)}, {int(generation)}, {int(turn)}, {q(action)}, "
                f"{q(intent)}, {q(target)}, {q(json.dumps(card_ids, ensure_ascii=False))}, "
                f"{q(json.dumps(deltas, ensure_ascii=False, sort_keys=True))}, {q(narrative[:4000])}, "
                f"{q(utc_now())})"
            )
            self.connection.commit()
        return ledger_id

    def ledger(self, player_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where = "" if not player_id else f" WHERE player_id={q(player_id)}"
        with self.lock:
            cursor = self._cursor()
            cursor.execute(
                "SELECT ledger_id, player_id, generation, turn, action, intent, target, "
                f"card_ids, deltas_json, narrative, created_at FROM inn_ledger{where} "
                f"ORDER BY created_at DESC LIMIT {max(1, min(int(limit), 100))}"
            )
            rows = list(cursor.fetchall())
        columns = (
            "ledger_id",
            "player_id",
            "generation",
            "turn",
            "action",
            "intent",
            "target",
            "card_ids",
            "deltas_json",
            "narrative",
            "created_at",
        )
        result = []
        for row in rows:
            item = dict(zip(columns, row, strict=True))
            try:
                item["card_ids"] = json.loads(item["card_ids"])
                item["deltas"] = json.loads(item.pop("deltas_json"))
            except Exception:
                pass
            result.append(item)
        return result

    def stats(self) -> dict[str, Any]:
        self.ensure_alive()

        def scalar(sql: str) -> int:
            rows = self._execute(sql)
            return int(rows[0][0]) if rows else 0

        try:
            version_rows = self._execute("SHOW VARIABLES LIKE 'version'")
            version = version_rows[0][1] if version_rows else "unknown"
        except Exception:
            version = "unknown"
        return {
            "engine": "seekdb (OceanBase embedded)",
            "version": version,
            "cards": self.card_count(),
            "card_kinds": self.card_kinds(),
            "plans": scalar("SELECT COUNT(*) FROM inn_plans"),
            "ledger": scalar("SELECT COUNT(*) FROM inn_ledger"),
            "latest_ledger": self.ledger(limit=3),
        }
