"""对运行中的客栈后端做一次可复现验收，输出 evidence/live-verification.json。"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv("GRUDGE_INN_URL", "http://127.0.0.1:8787").rstrip("/")
PLAYER = "review-demo"


def call(path: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.status, response.read().decode("utf-8")


def post(path: str, body: str, player: str) -> tuple[int, str]:
    return call(
        path,
        data=body.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8", "X-Player-Id": player},
    )


def post_json(path: str, payload: dict) -> tuple[int, str]:
    return call(
        path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def main() -> int:
    checks: list[dict] = []

    status, health_raw = call("/health")
    health = json.loads(health_raw)
    checks.append({"name": "health", "ok": status == 200 and health["powercontext"]["ready"] and health["seekdb"]["ready"], "detail": health})

    _, reset_raw = post_json("/v1/reset", {"player_id": PLAYER})
    reset = json.loads(reset_raw)
    checks.append({"name": "reset", "ok": reset.get("ok") is True, "detail": {"generation": reset.get("generation")}})

    turns = [
        (
            "我把阿福的鞋藏到房梁上",
            "阿福光着一只脚站在梯子下，脸从耳朵红到脖子。柳三娘从柜台后抬起眼，算盘珠子停了一拍：“房梁上的鞋，自己取下来。”阿福刚要搬梯子，梁上那只八哥忽然喊了一声：“阿福偷吃！”满堂客人都笑了。柳三娘却没笑，只把账本翻到新的一页。",
        ),
        (
            "给柳三娘送一碟桂花糕，顺便夸她年轻",
            "你把桂花糕放在柜台上，说三娘看着比门外那株桂花还年轻。柳三娘手一顿，糕没接，先拿抹布把柜台擦了三遍。阿福在旁边憋笑，被她一眼瞪回去。她终于捏起一块，咬了一小口，含糊道：“甜了。”可那碟糕，最后一块也没剩。",
        ),
        (
            "我道歉，对不起，我不该整阿福",
            "你老老实实低头认错。阿福愣了半天，把抹布往肩上一搭：“其实……鞋我早找着了。”柳三娘哼了一声，把一碗热茶推到你面前，茶面上漂着两片桂花。她没说话，只把账本上“阿福的鞋”那一行划掉，又在旁边写了三个小字：看表现。",
        ),
    ]

    turn_results = []
    for action, narrative in turns:
        _, brief = post("/v1/turn/prepare?format=text", action, PLAYER)
        assert "【判定】" in brief, brief
        assert "【可用素材】" in brief, brief
        _, reply = post("/v1/turn/commit", narrative, PLAYER)
        assert "好感" in reply and "记仇" in reply, reply
        assert "PowerContext" not in reply and "ledger-" not in reply, reply
        turn_results.append({"action": action, "brief_head": brief.splitlines()[:8], "reply": reply})
    checks.append({"name": "three_turns", "ok": len(turn_results) == 3, "detail": turn_results})

    _, state_raw = post_json("/v1/state", {"player_id": PLAYER})
    state = json.loads(state_raw)
    checks.append(
        {
            "name": "powercontext_state",
            "ok": state["state"]["turn"] == 3 and len(state["episodes"]) >= 3,
            "detail": {
                "turn": state["state"]["turn"],
                "stats": state["state"]["stats"],
                "episodes": len(state["episodes"]),
                "scope_id": state["scope_id"],
            },
        }
    )

    _, stats_raw = call("/v1/stats")
    stats = json.loads(stats_raw)
    checks.append(
        {
            "name": "seekdb_cards",
            "ok": stats["seekdb"]["cards"] >= 40,
            "detail": {
                "version": stats["seekdb"]["version"],
                "cards": stats["seekdb"]["cards"],
                "kinds": stats["seekdb"]["card_kinds"],
                "ledger": stats["seekdb"]["ledger"],
            },
        }
    )

    ok = all(item["ok"] for item in checks)
    payload = {
        "ok": ok,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": BASE,
        "player_id": PLAYER,
        "checks": checks,
    }
    out = ROOT / "evidence" / "live-verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": ok, "checks": [{"name": c["name"], "ok": c["ok"]} for c in checks]}, ensure_ascii=False, indent=2))
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
