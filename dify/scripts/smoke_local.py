"""不依赖 PowerContext 服务的本地冒烟测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ensure_runtime_dirs  # noqa: E402
from app.game import GameEngine  # noqa: E402
from app.memory import LocalMemory  # noqa: E402
from app.store import Store  # noqa: E402


def main() -> int:
    ensure_runtime_dirs()
    store = Store(Path.home() / ".local" / "share" / "grudge-inn-smoke" / "seekdb")
    engine = GameEngine(store, LocalMemory())
    print("cards:", store.card_count(), store.card_kinds())
    for action in [
        "我把阿福的鞋藏到房梁上",
        "给柳三娘送一碟桂花糕，顺便夸她年轻",
        "偷偷翻开柜台的账本",
        "我道歉，对不起，我不该整阿福",
        "看看状态",
    ]:
        prepared = engine.prepare("smoke-player", action)
        print("\nACTION", action)
        print("BRIEF\n", prepared["scene_brief"][:600])
        reply = engine.commit("smoke-player", f"这是对“{action}”的测试叙述。柳三娘抬了抬眼皮。")
        print("REPLY\n", reply[:500])
    print("\nSTATS", json.dumps(store.stats(), ensure_ascii=False, indent=2)[:1200])
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
