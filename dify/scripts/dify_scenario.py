"""跑一遍 Dify 端的验收样例，并把回答、会话 ID、PowerContext 状态写入 evidence/。

前置：
- Dify API 在 http://127.0.0.1:5001
- 客栈后端在 http://127.0.0.1:8787
- scripts/bootstrap_dify.py 已生成 ~/.local/share/grudge-inn/dify-app.json
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_FILE = Path.home() / ".local" / "share" / "grudge-inn" / "dify-app.json"
DIFY = os.getenv("DIFY_API_URL", "http://127.0.0.1:5001").rstrip("/")
INN = os.getenv("GRUDGE_INN_URL", "http://127.0.0.1:8787").rstrip("/")


def http_json(url: str, payload: dict, token: str | None = None, timeout: int = 120) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def chat(api_key: str, player_id: str, query: str, conversation_id: str = "") -> dict:
    body = {
        "inputs": {"player_id": player_id},
        "query": query,
        "response_mode": "blocking",
        "conversation_id": conversation_id,
        "user": "reviewer",
    }
    response = http_json(f"{DIFY}/v1/chat-messages", body, api_key)
    return {
        "query": query,
        "answer": response.get("answer", ""),
        "conversation_id": response.get("conversation_id", ""),
        "message_id": response.get("message_id", ""),
    }


def state(player_id: str) -> dict:
    return http_json(f"{INN}/v1/state", {"player_id": player_id})


def stats() -> dict:
    with urllib.request.urlopen(f"{INN}/v1/stats", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    app = json.loads(APP_FILE.read_text(encoding="utf-8"))
    api_key = app["api_key"]
    player = "dify-review"
    fresh = "dify-fresh"

    # 清掉上一轮演示，保证从“初入江湖”开始
    http_json(f"{INN}/v1/reset", {"player_id": player})
    http_json(f"{INN}/v1/reset", {"player_id": fresh})
    http_json(f"{INN}/v1/reset", {"player_id": "王志浩"})

    turns = []
    conversation_id = ""
    for query in [
        "我把阿福的鞋藏到房梁上",
        "给柳三娘送一碟桂花糕，顺便夸她年轻",
        "我道歉，对不起，我不该整阿福",
    ]:
        result = chat(api_key, player, query, conversation_id)
        conversation_id = result["conversation_id"]
        turns.append(result)
        print(f"[turn] {query} -> {result['answer'][:80]}...")

    # 新会话，同一个玩家：应该能回扣旧事
    memory_session = chat(api_key, player, "我回来了，柳三娘还记不记得我")
    # 新会话，新玩家：不应该知道旧事
    fresh_session = chat(api_key, fresh, "我回来了，柳三娘还记不记得我")
    # 中文玩家名：Dify 的 HTTP 节点不能把中文放进 header，必须走 query/body
    chinese_session = chat(api_key, "王志浩", "我把阿福的鞋藏到房梁上")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dify": DIFY,
        "app_id": app.get("app_id"),
        "player_id": player,
        "turns": turns,
        "cross_session_same_player": memory_session,
        "cross_session_new_player": fresh_session,
        "chinese_player": chinese_session,
        "powercontext_state": state(player),
        "seekdb_stats": stats(),
    }
    out = ROOT / "evidence" / "dify-run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Dify 端验收记录",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- Dify：`{DIFY}`",
        f"- app_id：`{payload['app_id']}`",
        f"- 玩家：`{player}`",
        "",
        "## 连续三回合",
        "",
    ]
    for index, turn in enumerate(turns, 1):
        md.extend([f"### 第 {index} 回合", "", f"**输入**：{turn['query']}", "", turn["answer"], ""])
    md.extend(
        [
            "## 跨会话：同一玩家",
            "",
            f"**输入**：{memory_session['query']}",
            "",
            memory_session["answer"],
            "",
            "## 跨会话：新玩家",
            "",
            f"**输入**：{fresh_session['query']}",
            "",
            fresh_session["answer"],
            "",
            "## 中文玩家名",
            "",
            "**玩家**：`王志浩`",
            "",
            f"**输入**：{chinese_session['query']}",
            "",
            chinese_session["answer"],
            "",
            "## PowerContext 状态",
            "",
            f"- scope_id：`{payload['powercontext_state'].get('scope_id')}`",
            f"- turn：{payload['powercontext_state']['state'].get('turn')}",
            f"- episodes：{len(payload['powercontext_state'].get('episodes', []))}",
            f"- stats：`{json.dumps(payload['powercontext_state']['state'].get('stats'), ensure_ascii=False)}`",
            "",
            "## seekdb",
            "",
            f"- version：`{payload['seekdb_stats']['seekdb'].get('version')}`",
            f"- cards：{payload['seekdb_stats']['seekdb'].get('cards')}",
            f"- plans：{payload['seekdb_stats']['seekdb'].get('plans')}",
            f"- ledger：{payload['seekdb_stats']['seekdb'].get('ledger')}",
            "",
        ]
    )
    (ROOT / "evidence" / "dify-run.md").write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {out}")
    print(f"wrote {ROOT / 'evidence' / 'dify-run.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
