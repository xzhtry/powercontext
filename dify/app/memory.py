"""PowerContext 记忆层。

每个玩家一个 Scope。两类 Memory entry：

- ``inn-state``：最新客栈状态（回合、属性、NPC 态度、称号）。
- ``inn-episode``：每个回合发生过的行动与结果，跨会话回放。

加载时取 generation 最大的状态；同一 generation 内取 turn 最大的状态。
这样即使不删除旧记忆，也能通过“新一代”实现重开。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.config import SCOPE_FILE
from app.store import utc_now

STATE_PREFIX = "GRUDGE_INN_STATE_V1\n"
EPISODE_PREFIX = "GRUDGE_INN_EPISODE_V1\n"
STATE_KIND = "inn-state"
EPISODE_KIND = "inn-episode"

DEFAULT_STATE = {
    "schema": "grudge-inn.state.v1",
    "generation": 1,
    "turn": 0,
    "stats": {"favor": 20, "grudge": 10, "chaos": 0, "silver": 30, "reputation": 10},
    "npcs": {
        "柳三娘": {"favor": 10, "grudge": 0},
        "阿福": {"favor": 20, "grudge": 0},
        "老周": {"favor": 0, "grudge": 0},
        "乌云": {"favor": 30, "grudge": 0},
        "老陈": {"favor": 0, "grudge": 0},
    },
    "flags": [],
    "title": "初入江湖",
    "ending": None,
    "last_scene": "",
    "updated_at": None,
}


class PowerContextError(RuntimeError):
    pass


class PowerContextClient:
    def __init__(self, base_url: str, *, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise PowerContextError(f"PowerContext {path} HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            raise PowerContextError(f"无法连接 PowerContext ({self.base_url})：{error}") from error

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/health/ready", timeout=3) as response:
                return response.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------
    def _scope_cache(self) -> dict[str, str]:
        if not SCOPE_FILE.is_file():
            return {}
        try:
            data = json.loads(SCOPE_FILE.read_text(encoding="utf-8"))
            return {str(key): str(value) for key, value in data.items()}
        except Exception:
            return {}

    def _save_scope(self, player_id: str, scope_id: str) -> None:
        SCOPE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cache = self._scope_cache()
        cache[player_id] = scope_id
        SCOPE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_scope(self, player_id: str) -> str:
        cached = self._scope_cache().get(player_id)
        if cached:
            return cached
        response = self._post(
            "/v1/scopes",
            {
                "title": f"记仇客栈 · {player_id}",
                "summary": "Dify × PowerContext 互动客栈：玩家状态、NPC 态度与回合记忆",
                "idempotency_key": f"grudge-inn-{player_id}",
            },
        )
        scope_id = response.get("scope_id")
        if not scope_id:
            raise PowerContextError(f"创建 Scope 失败：{response}")
        self._save_scope(player_id, str(scope_id))
        return str(scope_id)

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------
    def list_entries(self, scope_id: str) -> list[dict[str, Any]]:
        response = self._post("/v1/memory/entries/list", {"scope_id": scope_id, "limit": 100})
        entries = response.get("entries", [])
        return [entry for entry in entries if isinstance(entry, dict)]

    def load(self, player_id: str) -> dict[str, Any]:
        scope_id = self.ensure_scope(player_id)
        entries = self.list_entries(scope_id)
        states: list[dict[str, Any]] = []
        episodes: list[dict[str, Any]] = []
        for entry in entries:
            text = str(entry.get("text", ""))
            if entry.get("kind") == STATE_KIND and text.startswith(STATE_PREFIX):
                try:
                    states.append(json.loads(text[len(STATE_PREFIX) :]))
                except json.JSONDecodeError:
                    continue
            if entry.get("kind") == EPISODE_KIND and text.startswith(EPISODE_PREFIX):
                try:
                    episodes.append(json.loads(text[len(EPISODE_PREFIX) :]))
                except json.JSONDecodeError:
                    continue
        if states:
            state = max(states, key=lambda item: (int(item.get("generation", 1)), int(item.get("turn", 0))))
        else:
            state = json.loads(json.dumps(DEFAULT_STATE, ensure_ascii=False))
        generation = int(state.get("generation", 1))
        state["source"] = "powercontext"
        state["scope_id"] = scope_id
        current_episodes = [
            episode
            for episode in episodes
            if int(episode.get("generation", 1)) == generation
            and int(episode.get("turn", 0)) > 0
            and episode.get("intent") != "reset"
        ]
        current_episodes.sort(key=lambda item: int(item.get("turn", 0)))
        return {
            "state": state,
            "episodes": current_episodes[-6:],
            "scope_id": scope_id,
            "memory_entries": len(entries),
            "state_entries": len(states),
            "episode_entries": len(episodes),
        }

    def _remember(self, scope_id: str, kind: str, text: str, reason: str) -> dict[str, Any]:
        return self._post(
            "/v1/memory/remember",
            {"scope_id": scope_id, "kind": kind, "text": text, "reason": reason},
        )

    def save_turn(
        self,
        player_id: str,
        state: dict[str, Any],
        episode: dict[str, Any],
    ) -> dict[str, Any]:
        scope_id = self.ensure_scope(player_id)
        state_text = STATE_PREFIX + json.dumps(state, ensure_ascii=False, sort_keys=True)
        episode_text = EPISODE_PREFIX + json.dumps(episode, ensure_ascii=False, sort_keys=True)
        state_response = self._remember(
            scope_id,
            STATE_KIND,
            state_text,
            f"记仇客栈：{player_id} 第 {state.get('turn')} 回合状态",
        )
        episode_response = self._remember(
            scope_id,
            EPISODE_KIND,
            episode_text,
            f"记仇客栈：{player_id} 第 {episode.get('turn')} 回合剧情记忆",
        )
        record_ids = []
        for response in (state_response, episode_response):
            for record in response.get("records", []) or []:
                if record.get("record_id"):
                    record_ids.append(record["record_id"])
        return {"scope_id": scope_id, "record_ids": record_ids}

    def reset(self, player_id: str) -> dict[str, Any]:
        loaded = self.load(player_id)
        state = loaded["state"]
        generation = int(state.get("generation", 1)) + 1
        fresh = json.loads(json.dumps(DEFAULT_STATE, ensure_ascii=False))
        fresh.update(
            {
                "generation": generation,
                "turn": 0,
                "updated_at": utc_now(),
                "reset_from": state.get("generation", 1),
            }
        )
        self.save_turn(
            player_id,
            fresh,
            {
                "generation": generation,
                "turn": 0,
                "action": "/reset",
                "intent": "reset",
                "target": "客栈",
                "outcome": "你把客栈的账本翻到最后一页，重新写下了第一行。",
                "created_at": utc_now(),
            },
        )
        return {"state": fresh, "scope_id": loaded["scope_id"], "generation": generation}


class LocalMemory:
    """测试用内存实现，接口与 PowerContextClient 对齐。"""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}

    def ensure_scope(self, player_id: str) -> str:
        return f"local-{player_id}"

    def load(self, player_id: str) -> dict[str, Any]:
        item = self.data.get(player_id)
        if not item:
            state = json.loads(json.dumps(DEFAULT_STATE, ensure_ascii=False))
            return {
                "state": state,
                "episodes": [],
                "scope_id": self.ensure_scope(player_id),
                "memory_entries": 0,
                "state_entries": 0,
                "episode_entries": 0,
            }
        return {
            "state": item["state"],
            "episodes": item["episodes"],
            "scope_id": self.ensure_scope(player_id),
            "memory_entries": len(item["episodes"]) + 1,
            "state_entries": 1,
            "episode_entries": len(item["episodes"]),
        }

    def save_turn(self, player_id: str, state: dict[str, Any], episode: dict[str, Any]) -> dict[str, Any]:
        item = self.data.setdefault(player_id, {"state": state, "episodes": []})
        item["state"] = state
        item["episodes"].append(episode)
        item["episodes"] = item["episodes"][-20:]
        return {"scope_id": self.ensure_scope(player_id), "record_ids": [f"local-{len(item['episodes'])}"]}

    def reset(self, player_id: str) -> dict[str, Any]:
        loaded = self.load(player_id)
        generation = int(loaded["state"].get("generation", 1)) + 1
        fresh = json.loads(json.dumps(DEFAULT_STATE, ensure_ascii=False))
        fresh["generation"] = generation
        fresh["turn"] = 0
        fresh["reset_from"] = loaded["state"].get("generation", 1)
        self.data[player_id] = {"state": fresh, "episodes": []}
        return {"state": fresh, "scope_id": self.ensure_scope(player_id), "generation": generation}
