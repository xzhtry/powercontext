from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.game import GameEngine, classify, find_target, severity_of  # noqa: E402
from app.memory import LocalMemory  # noqa: E402
from app.store import Store  # noqa: E402


@pytest.fixture()
def engine(tmp_path: Path):
    store = Store(tmp_path / "seekdb")
    game = GameEngine(store, LocalMemory())
    yield game
    store.close()


def test_classification_intent_and_target() -> None:
    assert classify("我把阿福的鞋藏到房梁上")[0] == "prank"
    assert classify("偷偷翻开柜台的账本")[0] == "theft"
    assert classify("我道歉，对不起")[0] == "apologize"
    assert classify("给柳三娘送一碟桂花糕")[0] == "help"
    assert classify("看看状态")[0] == "status"
    assert find_target("我把阿福的鞋藏到房梁上", "prank") == "阿福"
    assert find_target("偷偷翻开柜台的账本", "theft") == "柳三娘"
    assert severity_of("把账本烧了", "fight", "柳三娘") >= 4


def test_chinese_player_id(engine: GameEngine) -> None:
    prepared = engine.prepare("王志浩", "我把阿福的鞋藏到房梁上")
    assert prepared["player_id"] == "王志浩"
    assert "【玩家】王志浩" in prepared["scene_brief"]
    engine.commit("王志浩", "阿福光着一只脚站在梯子下。")
    assert engine.memory.load("王志浩")["state"]["turn"] == 1


def test_silver_can_buy_a_gift(engine: GameEngine) -> None:
    prepared = engine.prepare("tester", "买一碟桂花糕送给柳三娘")
    assert prepared["intent"] == "buy"
    assert prepared["target"] == "柳三娘"
    engine.commit("tester", "你把桂花糕递过去，柳三娘接下了。")
    state = engine.memory.load("tester")["state"]
    assert state["stats"]["silver"] == 25
    assert state["stats"]["favor"] > 20


def test_cannot_buy_without_silver(engine: GameEngine) -> None:
    loaded = engine.memory.load("poor")
    loaded["state"]["stats"]["silver"] = 1
    engine.memory.data["poor"] = {"state": loaded["state"], "episodes": []}
    prepared = engine.prepare("poor", "买一碟桂花糕")
    assert "买不起" in prepared["scene_brief"]
    engine.commit("poor", "你摸遍钱袋，什么也没买成。")
    assert engine.memory.load("poor")["state"]["stats"]["silver"] == 1


def test_question_is_treated_as_dialogue(engine: GameEngine) -> None:
    prepared = engine.prepare("tester", "为什么")
    assert prepared["intent"] == "chat"
    assert prepared["target"] == "柳三娘"
    assert "你把问题丢给柳三娘" in prepared["scene_brief"]


def test_seekdb_has_cards(engine: GameEngine) -> None:
    assert engine.store.card_count() >= 40
    cards = engine.store.search_cards("会唱歌的茶壶", tags=["茶壶"], limit=3)
    assert cards
    assert any("茶壶" in card["title"] for card in cards)


def test_prepare_commit_and_memory(engine: GameEngine) -> None:
    prepared = engine.prepare("tester", "我把阿福的鞋藏到房梁上")
    assert prepared["intent"] == "prank"
    assert prepared["target"] == "阿福"
    assert "阿福的破鞋" in prepared["scene_brief"]
    assert "第 1 回合" in prepared["scene_brief"]

    reply = engine.commit("tester", "阿福光着一只脚站在梯子下，柳三娘把算盘往柜台上一拍。")
    assert "第 1 回合" in reply
    assert "好感" in reply and "记仇" in reply
    assert "PowerContext" not in reply and "ledger-" not in reply
    assert "阿福的破鞋" in reply or "阿福" in reply

    loaded = engine.memory.load("tester")
    assert loaded["state"]["turn"] == 1
    assert loaded["state"]["stats"]["grudge"] > 10
    assert len(loaded["episodes"]) == 1


def test_second_turn_has_callback(engine: GameEngine) -> None:
    prepared = engine.prepare("tester", "我把阿福的鞋藏到房梁上")
    engine.commit("tester", "阿福光着一只脚站在梯子下。")
    second = engine.prepare("tester", "我回来了，柳三娘还记不记得我")
    assert "前情记忆" in second["scene_brief"]
    assert "第1回合" in second["scene_brief"]


def test_status_does_not_advance_state(engine: GameEngine) -> None:
    engine.prepare("tester", "我把阿福的鞋藏到房梁上")
    engine.commit("tester", "阿福光着一只脚站在梯子下。")
    before = engine.memory.load("tester")["state"]["turn"]
    engine.prepare("tester", "看看状态")
    reply = engine.commit("tester", "你摊开账本，墨迹还没干。")
    after = engine.memory.load("tester")["state"]["turn"]
    assert before == after == 1
    assert "PowerContext" not in reply and "新记忆" not in reply


def test_reset_creates_new_generation(engine: GameEngine) -> None:
    prepared = engine.prepare("tester", "我把阿福的鞋藏到房梁上")
    engine.commit("tester", "阿福光着一只脚站在梯子下。")
    reset_plan = engine.prepare("tester", "/reset")
    assert reset_plan["intent"] == "reset"
    engine.commit("tester", "你重新推开客栈的门，门轴响了一声。")
    loaded = engine.memory.load("tester")
    assert loaded["state"]["turn"] == 1
    assert loaded["state"]["generation"] == 2
    assert loaded["episodes"][-1]["action"] == "/reset"


def test_duplicate_commit_is_idempotent(engine: GameEngine) -> None:
    engine.prepare("tester", "我把阿福的鞋藏到房梁上")
    first = engine.commit("tester", "阿福光着一只脚站在梯子下。")
    second = engine.commit("tester", "另一段不应该被采用的文字。")
    assert first == second
