"""PowerContext 状态读写。

任务进展与验证结果以 Memory entry（kind=task-state）保存到 PowerContext Server，
下一次运行（包括模块重启后的新进程）通过 entries/list 读取，并用于后续上下文。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from sddctx.config import Settings
from sddctx.util import read_json, utc_now, write_json

STATE_PREFIX = "SDDCTX_STATE_V1\n"
STATE_KIND = "task-state"


class PowerContextError(RuntimeError):
    """PowerContext 不可用或返回了非预期结果。"""


class PowerContextClient:
    def __init__(self, base_url: str, *, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise PowerContextError(f"PowerContext {path} 返回 HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise PowerContextError(
                f"无法连接 PowerContext ({self.base_url})。请先启动：bash scripts/start_powercontext.sh"
            ) from error

    def ensure_scope(self, settings: Settings) -> str:
        if settings.scope_file.is_file():
            scope_id = read_json(settings.scope_file).get("scope_id")
            if scope_id:
                return str(scope_id)
        response = self._post(
            "/v1/scopes",
            {
                "title": "sddctx invoicehub",
                "summary": "SDD 上下文任务状态：invoicehub 发票查询服务",
                "idempotency_key": "sddctx-invoicehub",
            },
        )
        scope_id = response.get("scope_id")
        if not scope_id:
            raise PowerContextError(f"创建 Scope 失败：{response}")
        write_json(settings.scope_file, {"scope_id": scope_id, "created_at": utc_now()})
        return str(scope_id)

    def list_state_entries(self, scope_id: str) -> list[dict[str, Any]]:
        response = self._post("/v1/memory/entries/list", {"scope_id": scope_id, "limit": 100})
        entries = response.get("entries", [])
        return [entry for entry in entries if entry.get("kind") == STATE_KIND and entry.get("text", "").startswith(STATE_PREFIX)]

    def load_state(self, settings: Settings) -> dict[str, Any]:
        scope_id = self.ensure_scope(settings)
        candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        for entry in self.list_state_entries(scope_id):
            try:
                state = json.loads(entry["text"][len(STATE_PREFIX) :])
            except json.JSONDecodeError:
                continue
            candidates.append((int(state.get("run_seq", 0)), state, entry))
        if not candidates:
            state = {
                "schema": "sddctx.task_state.v1",
                "run_seq": 0,
                "status": "empty",
                "completed": [],
                "pending": [],
                "verifications": [],
                "source": "powercontext",
                "scope_id": scope_id,
                "updated_at": None,
            }
            write_json(settings.state_dir / "latest-empty.json", state)
            return state
        _, state, entry = max(candidates, key=lambda item: item[0])
        state["source"] = "powercontext"
        state["scope_id"] = scope_id
        state["entry"] = entry.get("artifact")
        write_json(settings.state_dir / f"{state.get('task_id', 'unknown')}.json", state)
        return state

    def save_state(self, settings: Settings, task_id: str, state: dict[str, Any]) -> dict[str, Any]:
        scope_id = self.ensure_scope(settings)
        previous = self.load_state(settings)
        run_seq = int(previous.get("run_seq", 0)) + 1
        record = dict(state)
        record.update(
            {
                "schema": "sddctx.task_state.v1",
                "task_id": task_id,
                "run_seq": run_seq,
                "source": "powercontext",
                "scope_id": scope_id,
                "updated_at": utc_now(),
            }
        )
        text = STATE_PREFIX + json.dumps(record, ensure_ascii=False, sort_keys=True)
        response = self._post(
            "/v1/memory/remember",
            {
                "scope_id": scope_id,
                "kind": STATE_KIND,
                "text": text,
                "reason": f"SDD 任务 {task_id} 第 {run_seq} 次运行的任务进展与验证结果",
            },
        )
        records = response.get("records") or []
        if records:
            record["entry"] = records[0].get("artifact")
        write_json(settings.state_dir / f"{task_id}.json", record)
        return record
