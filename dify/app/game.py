"""客栈游戏引擎。

设计原则：**先判定，后叙述**。
Dify 在 LLM 之前调用 ``prepare``，拿到已经算好的成败、数值变化和素材；
LLM 只负责把“事实”写成好玩的场景。这样模型不会改写游戏规则，也便于复现和测试。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from copy import deepcopy
from typing import Any

from app.memory import DEFAULT_STATE, LocalMemory, PowerContextClient
from app.store import Store, utc_now

PLAYER_RE = re.compile(r"[^0-9A-Za-z_\-\u4e00-\u9fff]")
VALID_INTENTS = {
    "prank",
    "theft",
    "fight",
    "help",
    "apologize",
    "compliment",
    "probe",
    "chat",
    "status",
    "reset",
}

INTENT_LABELS = {
    "prank": "恶作剧",
    "theft": "顺手牵羊",
    "fight": "动手",
    "help": "帮忙",
    "apologize": "道歉",
    "compliment": "说好话",
    "probe": "打听",
    "buy": "柜台消费",
    "chat": "闲聊",
    "status": "看状态",
    "reset": "重开",
}

# 顺序只用于同分时决定优先级；分数由关键词命中累加。
INTENT_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "reset": [("/reset", 20), ("重置", 20), ("重开", 20), ("重新开始", 20), ("从头再来", 18)],
    "status": [("状态", 14), ("面板", 14), ("战绩", 14), ("记仇值", 14), ("好感", 8), ("结算", 12)],
    "buy": [
        ("买", 12),
        ("来一", 8),
        ("请客", 14),
        ("请柳三娘喝", 14),
        ("请阿福", 12),
        ("赏", 10),
        ("打赏", 12),
        ("付账", 10),
        ("买单", 12),
        ("结账", 8),
        ("住店", 8),
        ("开一间", 8),
    ],
    "apologize": [
        ("道歉", 16),
        ("赔罪", 16),
        ("认错", 16),
        ("对不起", 16),
        ("赔不是", 14),
        ("求和", 10),
        ("服软", 10),
        ("请罪", 14),
        ("赔钱", 8),
    ],
    "theft": [
        ("偷", 12),
        ("顺走", 12),
        ("摸走", 12),
        ("窃", 12),
        ("盗", 12),
        ("撬", 12),
        ("偷看", 10),
        ("翻账", 10),
        ("查账", 8),
        ("拿走", 8),
        ("顺", 5),
    ],
    "fight": [
        ("揍", 14),
        ("踢", 12),
        ("踹", 14),
        ("掀", 10),
        ("砸", 14),
        ("烧", 14),
        ("砍", 14),
        ("刺", 10),
        ("推倒", 12),
        ("摔", 8),
        ("骂", 8),
        ("吼", 6),
        ("拍桌", 10),
        ("打", 7),
    ],
    "prank": [
        ("藏", 12),
        ("偷换", 12),
        ("换掉", 10),
        ("涂", 10),
        ("贴", 8),
        ("塞", 8),
        ("吓", 10),
        ("骗", 10),
        ("整", 8),
        ("恶作剧", 16),
        ("绊", 10),
        ("泼", 10),
        ("拆", 10),
        ("画", 6),
        ("挂", 6),
        ("绑", 10),
        ("调包", 14),
        ("辣椒", 8),
        ("痒", 8),
        ("臭", 6),
        ("唱歌", 4),
        ("学舌", 6),
    ],
    "help": [
        ("帮忙", 12),
        ("帮", 6),
        ("修", 10),
        ("补", 8),
        ("找", 6),
        ("救", 10),
        ("送", 6),
        ("打扫", 14),
        ("收拾", 8),
        ("请客", 12),
        ("买单", 12),
        ("照顾", 10),
        ("喂", 8),
        ("治", 8),
        ("安慰", 10),
        ("还", 4),
        ("擦", 6),
        ("劈柴", 12),
        ("挑水", 12),
    ],
    "compliment": [
        ("夸", 14),
        ("赞", 10),
        ("漂亮", 10),
        ("年轻", 8),
        ("好看", 10),
        ("敬", 6),
        ("佩服", 10),
        ("恭维", 12),
        ("捧", 6),
        ("说好话", 14),
        ("唱", 3),
    ],
    "probe": [
        ("打听", 14),
        ("观察", 10),
        ("问问", 8),
        ("问", 6),
        ("聊聊", 8),
        ("聊", 5),
        ("探", 6),
        ("听", 4),
        ("闻", 4),
        ("套话", 12),
        ("找线索", 12),
        ("看看", 5),
    ],
}

TARGET_ALIASES: list[tuple[str, list[str]]] = [
    ("柳三娘", ["柳三娘", "三娘", "老板娘", "掌柜"]),
    ("阿福", ["阿福", "店小二", "小二"]),
    ("老周", ["老周", "说书人"]),
    ("乌云", ["乌云", "黑猫", "猫"]),
    ("老陈", ["老陈", "捕快", "差役"]),
    ("客人", ["客人", "客官", "住店"]),
]

TARGET_HINTS: list[tuple[str, list[str]]] = [
    ("柳三娘", ["账本", "银簪", "茶壶", "桂花糕", "算盘", "屋顶", "西厢房", "灶王爷"]),
    ("阿福", ["鞋", "八哥", "菜刀", "醒酒汤", "辣椒", "泻药", "芦花鸡"]),
    ("老周", ["折扇", "醒木", "说书", "藏宝图", "宝藏"]),
    ("乌云", ["鱼干", "猫"]),
    ("老陈", ["腰牌", "查房", "官印", "马"]),
]

BASE_SEVERITY = {
    "buy": 1,
    "prank": 2,
    "theft": 3,
    "fight": 4,
    "help": 1,
    "apologize": 1,
    "compliment": 1,
    "probe": 1,
    "chat": 1,
    "status": 1,
    "reset": 1,
}

STRONG_WORDS = ["砸", "烧", "砍", "刺", "毒", "泻药", "炸药", "刀", "杀", "推倒", "掀桌"]


def clean_player_id(raw: str | None) -> str:
    value = (raw or "").strip() or "demo-player"
    value = PLAYER_RE.sub("-", value)
    value = value.strip("-")[:64]
    return value or "demo-player"


def clean_action(raw: str | None) -> str:
    value = (raw or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value[:500]


def clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def _hits(action: str, keywords: list[tuple[str, int]]) -> int:
    return sum(weight for word, weight in keywords if word in action)


def classify(action: str) -> tuple[str, int]:
    scores = {intent: _hits(action, words) for intent, words in INTENT_KEYWORDS.items()}
    # “帮我藏起来”应该判成恶作剧；“偷看账本”应该判成偷，而不是打听。
    if "帮" in action and any(word in action for word in ("藏", "偷", "换", "吓", "骗")):
        scores["help"] = max(0, scores["help"] - 5)
    best = max(scores.values())
    if best <= 0:
        return "chat", 0
    priority = ["reset", "status", "apologize", "theft", "fight", "prank", "buy", "help", "compliment", "probe"]
    for intent in priority:
        if scores[intent] == best:
            return intent, best
    return "chat", best


def find_target(action: str, intent: str) -> str:
    for name, aliases in TARGET_ALIASES:
        if any(alias in action for alias in aliases):
            return name
    for name, hints in TARGET_HINTS:
        if any(hint in action for hint in hints):
            return name
    if intent in {"prank", "theft", "fight", "apologize", "compliment", "chat", "buy"}:
        return "柳三娘"
    if intent == "probe":
        return "老周"
    if intent == "help":
        return "客栈"
    return "客栈"


def severity_of(action: str, intent: str, target: str) -> int:
    score = BASE_SEVERITY.get(intent, 1)
    if any(word in action for word in STRONG_WORDS):
        score += 2
    if target == "老陈":
        score += 1
    if "轻" in action or "悄悄" in action:
        score -= 1
    return clamp(score, 1, 5)


def clean_action_phrase(action: str) -> str:
    value = action.strip().rstrip("。！？!?")
    for prefix in ("我觉得", "我想", "我要", "我打算", "我准备", "我", "俺", "本大爷", "本姑娘"):
        if value.startswith(prefix):
            value = value[len(prefix) :].lstrip("，, ")
            break
    return value[:32] + ("…" if len(value) > 32 else "")


def scene_name(state: dict[str, Any]) -> str:
    stats = state["stats"]
    if stats.get("grudge", 0) >= 70:
        return "杀气腾腾"
    if stats.get("chaos", 0) >= 60:
        return "鸡飞狗跳"
    if stats.get("favor", 0) >= 65:
        return "宾至如归"
    if stats.get("grudge", 0) >= 25:
        return "暗流涌动"
    if int(state.get("turn", 0)) % 5 == 0 and state.get("turn", 0) > 0:
        return "风雨欲来"
    return "大堂"


def _pick_line(lines: list[str], state: dict[str, Any], target: str) -> str:
    """按回合/数值轮换台词，避免每回合都重复同一句。"""

    if not lines:
        return ""
    stats = state.get("stats", {})
    turn = int(state.get("turn", 0))
    index = (turn + int(stats.get("grudge", 0)) + int(stats.get("favor", 0)) + len(target)) % len(lines)
    return lines[index]


def npc_line(target: str, state: dict[str, Any]) -> str:
    if target in {"客栈", ""}:
        target = "柳三娘"
    npc = state.get("npcs", {}).get(target, {})
    grudge = int(npc.get("grudge", state["stats"].get("grudge", 0)))
    favor = int(npc.get("favor", state["stats"].get("favor", 0)))
    turn = int(state.get("turn", 0))

    if target == "阿福":
        if grudge >= 60:
            return _pick_line(
                [
                    "阿福：您的茶。放心，这次我只加了半勺盐。",
                    "阿福：客官，后厨的刀我收起来了，您别找了。",
                    "阿福：您那鞋，我供在房梁上了，要取自己搬梯子。",
                ],
                state,
                target,
            )
        if favor >= 55:
            return _pick_line(
                [
                    "阿福：灶上给您留了碗面，趁热，别让三娘看见。",
                    "阿福：您的茶我兑了温水，知道您怕烫。",
                    "阿福：待会儿打烊，我给您留盏灯。",
                ],
                state,
                target,
            )
        if grudge >= 25:
            return _pick_line(
                [
                    "阿福：客官，您的鞋……算了，我自己找。",
                    "阿福：茶在桌上，盐在您手边，您自己看着办。",
                    "阿福：我这人记性不好，就记仇记得清。",
                ],
                state,
                target,
            )
        return _pick_line(
            [
                "阿福：客官，茶刚沏的，先坐？",
                "阿福：今儿的酱牛肉不错，给您切一盘？",
                "阿福：您先坐，茶马上来。",
            ],
            state,
            target,
        )

    if target == "老周":
        if grudge >= 50:
            return _pick_line(
                [
                    "老周：下一段书，就说《某客官夜宿记》，您猜主角是谁？",
                    "老周：醒木一拍，假的也能说成真的——您那点事，我可都记着。",
                ],
                state,
                target,
            )
        return _pick_line(
            [
                "老周：客官来得巧，正讲到后山那口井。",
                "老周：您听说没有？柳三娘当年那支银簪……",
                "老周：要听真事还是听热闹？真事得加钱。",
            ],
            state,
            target,
        )

    if target == "乌云":
        if favor >= 55:
            return _pick_line(
                [
                    "乌云：尾巴一甩，在你脚边卧下了。",
                    "乌云：叼来半条鱼干，放在你鞋边，像在还债。",
                ],
                state,
                target,
            )
        return _pick_line(
            [
                "乌云：看了你一眼，继续睡在账本上。",
                "乌云：从房梁上跳下来，绕着你走了半圈。",
            ],
            state,
            target,
        )

    if target == "老陈":
        if grudge >= 50:
            return _pick_line(
                [
                    "老陈：最近客栈不太平啊，我会常来。",
                    "老陈：腰牌拍在桌上，面汤溅出来两滴。",
                ],
                state,
                target,
            )
        return _pick_line(
            [
                "老陈：一碗阳春面，记衙门账上。",
                "老陈：查房。都把门开开。",
            ],
            state,
            target,
        )

    if target == "客人":
        return "客人：这客栈……怎么比江湖还险？"

    if grudge >= 75:
        return _pick_line(
            [
                "柳三娘：客官，您的茶——我特意多加了三勺盐。",
                "柳三娘：今晚西厢房给您留着，房梁上那根绳也留着。",
                "柳三娘：账本上您的名字，我已经描了三遍。",
            ],
            state,
            target,
        )
    if grudge >= 45:
        return _pick_line(
            [
                "柳三娘：账我记着，人也记着。",
                "柳三娘：客官，您的茶凉了，我给您换一碗——放心，没加东西。",
                "柳三娘：您今儿要是再手痒，后院的柴够您劈到天亮。",
            ],
            state,
            target,
        )
    if grudge >= 25:
        return _pick_line(
            [
                "柳三娘：房梁上那只鞋，您打算什么时候取下来？",
                "柳三娘：您这名字，我记在账本第三页。",
                "柳三娘：客官，茶钱先结一下？连上回的。",
            ],
            state,
            target,
        )
    if favor >= 60:
        return _pick_line(
            [
                "柳三娘：灶上给你留了碗面，趁热。",
                "柳三娘：今儿不收你茶钱，别声张。",
                "柳三娘：西厢房给你留着，窗纸刚糊过。",
            ],
            state,
            target,
        )
    if favor >= 30:
        return _pick_line(
            [
                "柳三娘：客官，今儿想吃什么？",
                "柳三娘：您来得勤，阿福都记住您口味了。",
                "柳三娘：茶刚沏的，坐吧。",
            ],
            state,
            target,
        )
    if turn >= 2:
        return _pick_line(
            [
                "柳三娘：客官，又来了？",
                "柳三娘：这回别再把鞋弄房梁上。茶钱先结一下？",
                "柳三娘：您这脸，我好像在哪本账上见过。",
            ],
            state,
            target,
        )
    return _pick_line(
        [
            "柳三娘：客官，今儿想吃点什么？",
            "柳三娘：先坐，茶马上来。",
        ],
        state,
        target,
    )


class GameEngine:
    def __init__(self, store: Store, memory: PowerContextClient | LocalMemory | None = None) -> None:
        self.store = store
        self.memory = memory or PowerContextClient("http://127.0.0.1:8766")
        self.lock = threading.RLock()

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def prepare(self, raw_player: str | None, raw_action: str | None) -> dict[str, Any]:
        player_id = clean_player_id(raw_player)
        action = clean_action(raw_action)
        if not action:
            raise ValueError("行动不能为空。写点什么，比如：我把阿福的鞋藏到房梁上。")

        with self.lock:
            self.store.ensure_alive()
            loaded = self.memory.load(player_id)
            state = loaded["state"]
            intent, _score = classify(action)

            if intent == "status":
                plan = self._status_plan(player_id, state, action)
            elif intent == "reset":
                plan = self._reset_plan(player_id, state)
            else:
                target = find_target(action, intent)
                severity = severity_of(action, intent, target)
                cards = self._pick_cards(action, intent, target)
                plan = self._normal_plan(player_id, state, loaded["episodes"], action, intent, target, severity, cards)

            plan["player_id"] = player_id
            plan["created_at"] = utc_now()
            plan["scene_brief"] = self._scene_brief(plan, state, loaded["episodes"])
            plan["plan_id"] = self.store.save_plan(player_id, plan)
            return {
                "ok": True,
                "player_id": player_id,
                "plan_id": plan["plan_id"],
                "intent": plan["intent"],
                "target": plan["target"],
                "turn": plan["turn"],
                "scene_brief": plan["scene_brief"],
                "cards": plan.get("cards", []),
                "memory": {
                    "scope_id": loaded["scope_id"],
                    "entries": loaded["memory_entries"],
                    "episodes": len(loaded["episodes"]),
                },
            }

    def commit(self, raw_player: str | None, narrative: str | None) -> str:
        player_id = clean_player_id(raw_player)
        story = self._sanitize_narrative(narrative)
        if not story:
            raise ValueError("叙述不能为空。")

        with self.lock:
            self.store.ensure_alive()
            plan = self.store.latest_open_plan(player_id)
            if not plan:
                latest = self.store.latest_plan(player_id)
                if latest and latest.get("committed") and latest.get("reply_markdown"):
                    return str(latest["reply_markdown"])
                raise ValueError("没有待提交的回合。请先调用 /v1/turn/prepare。")

            if plan["intent"] == "status":
                state = self.memory.load(player_id)["state"]
                reply = f"{story}\n\n---\n{self._status_panel(state, plan)}"
                self.store.mark_plan_committed(plan["plan_id"], reply)
                return reply

            if plan.get("reset"):
                state = deepcopy(DEFAULT_STATE)
                state.update(
                    {
                        "generation": int(plan["generation"]),
                        "turn": 1,
                        "updated_at": utc_now(),
                        "reset_from": plan.get("reset_from"),
                    }
                )
                plan["deltas"] = {}
                plan["npc_deltas"] = {}
                plan["turn"] = 1
            else:
                loaded = self.memory.load(player_id)
                state = loaded["state"]
                if int(state.get("generation", 1)) != int(plan["generation"]):
                    self.store.drop_open_plans(player_id)
                    raise ValueError("记忆代际已变化，请重新发送行动。")
                if int(state.get("turn", 0)) + 1 != int(plan["turn"]):
                    self.store.drop_open_plans(player_id)
                    raise ValueError("回合已推进，请重新发送行动。")

            self._apply_plan(state, plan)
            episode = {
                "generation": int(state["generation"]),
                "turn": int(state["turn"]),
                "action": plan["action"],
                "intent": plan["intent"],
                "target": plan["target"],
                "outcome": plan.get("outcome", ""),
                "deltas": plan.get("deltas", {}),
                "card_ids": plan.get("card_ids", []),
                "created_at": utc_now(),
            }
            memory_result = self.memory.save_turn(player_id, state, episode)
            ledger_id = self.store.add_ledger(
                player_id=player_id,
                generation=int(state["generation"]),
                turn=int(state["turn"]),
                action=plan["action"],
                intent=plan["intent"],
                target=plan["target"],
                card_ids=plan.get("card_ids", []),
                deltas=plan.get("deltas", {}),
                narrative=story,
            )
            reply = self._reply(story, state, plan, ledger_id, memory_result)
            self.store.mark_plan_committed(plan["plan_id"], reply)
            return reply

    def status(self, raw_player: str | None) -> dict[str, Any]:
        player_id = clean_player_id(raw_player)
        self.store.ensure_alive()
        loaded = self.memory.load(player_id)
        return {
            "ok": True,
            "player_id": player_id,
            "state": loaded["state"],
            "episodes": loaded["episodes"],
            "scope_id": loaded["scope_id"],
            "powercontext": {
                "entries": loaded["memory_entries"],
                "state_entries": loaded["state_entries"],
                "episode_entries": loaded["episode_entries"],
            },
        }

    def reset(self, raw_player: str | None) -> dict[str, Any]:
        player_id = clean_player_id(raw_player)
        with self.lock:
            self.store.ensure_alive()
            result = self.memory.reset(player_id)
            self.store.drop_open_plans(player_id)
            return {"ok": True, "player_id": player_id, **result}

    # ------------------------------------------------------------------
    # 计划构造
    # ------------------------------------------------------------------
    def _status_plan(self, player_id: str, state: dict[str, Any], action: str) -> dict[str, Any]:
        return {
            "generation": int(state["generation"]),
            "turn": int(state["turn"]),
            "action": action,
            "intent": "status",
            "target": "客栈",
            "severity": 1,
            "success": True,
            "caught": False,
            "cards": [],
            "card_ids": [],
            "deltas": {},
            "npc_deltas": {},
            "outcome": self._status_panel(state, {"target": "客栈"}),
            "retaliation": None,
            "ending": state.get("ending"),
            "title": state.get("title", "初入江湖"),
            "no_memory": True,
        }

    def _reset_plan(self, player_id: str, state: dict[str, Any]) -> dict[str, Any]:
        generation = int(state.get("generation", 1)) + 1
        return {
            "generation": generation,
            "reset_from": state.get("generation", 1),
            "reset": True,
            "turn": 1,
            "action": "/reset",
            "intent": "reset",
            "target": "客栈",
            "severity": 1,
            "success": True,
            "caught": False,
            "cards": [],
            "card_ids": [],
            "deltas": {},
            "npc_deltas": {},
            "outcome": "你把旧账本合上，推门重新走进客栈。柳三娘抬眼看了看你，像第一次见，又像什么都记得。",
            "retaliation": None,
            "ending": None,
            "title": "初入江湖",
        }

    def _normal_plan(
        self,
        player_id: str,
        state: dict[str, Any],
        episodes: list[dict[str, Any]],
        action: str,
        intent: str,
        target: str,
        severity: int,
        cards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generation = int(state.get("generation", 1))
        turn = int(state.get("turn", 0)) + 1
        success, caught, roll = self._roll(player_id, generation, turn, action, intent, severity)
        if intent == "buy" and not self._purchase(action, target, state)["affordable"]:
            success, caught = False, False
        card = cards[0] if cards else None
        outcome = self._outcome(action, intent, target, severity, success, caught, card, state)
        deltas, npc_deltas = self._deltas(action, intent, target, severity, success, caught, card, state)
        retaliation = self._retaliation(state, target, intent, severity, turn)
        if retaliation:
            deltas["chaos"] = int(deltas.get("chaos", 0)) + 2
            deltas["favor"] = int(deltas.get("favor", 0)) - 1
            npc_deltas.setdefault(target, {})
            npc_deltas[target]["grudge"] = int(npc_deltas[target].get("grudge", 0)) + 2
        ending, title = self._ending(state, deltas)
        return {
            "generation": generation,
            "turn": turn,
            "action": action,
            "intent": intent,
            "target": target,
            "severity": severity,
            "success": success,
            "caught": caught,
            "roll": round(roll, 4),
            "cards": cards,
            "card_ids": [card["card_id"] for card in cards] if card else [],
            "deltas": deltas,
            "npc_deltas": npc_deltas,
            "outcome": outcome,
            "retaliation": retaliation,
            "ending": ending,
            "title": title,
        }

    # ------------------------------------------------------------------
    # 判定与数值
    # ------------------------------------------------------------------
    def _roll(
        self,
        player_id: str,
        generation: int,
        turn: int,
        action: str,
        intent: str,
        severity: int,
    ) -> tuple[bool, bool, float]:
        digest = hashlib.sha256(f"{player_id}|{generation}|{turn}|{action}".encode("utf-8")).hexdigest()
        roll = int(digest[:8], 16) / 0xFFFFFFFF
        roll2 = int(digest[8:16], 16) / 0xFFFFFFFF
        chance = {
            "prank": 0.78,
            "theft": 0.58,
            "fight": 0.62,
            "help": 0.92,
            "buy": 1.0,
            "apologize": 0.96,
            "compliment": 1.0,
            "probe": 1.0,
            "chat": 1.0,
        }.get(intent, 0.9)
        if intent in {"prank", "theft", "fight"}:
            chance -= max(0, severity - 2) * 0.05
        success = roll < chance
        caught = False
        if intent in {"prank", "theft"}:
            if not success:
                caught = True
            elif roll2 < 0.22 + severity * 0.06:
                caught = True
        elif intent == "fight":
            caught = True
        return success, caught, roll

    def _purchase(self, action: str, target: str, state: dict[str, Any]) -> dict[str, Any]:
        silver = int(state.get("stats", {}).get("silver", 0))
        if "桂花糕" in action or "糕" in action:
            item, cost, favor, grudge = "一碟桂花糕", 5, 6, -3
            target = "柳三娘" if target == "客栈" else target
        elif "鱼干" in action:
            item, cost, favor, grudge = "一包鱼干", 3, 4, -1
            target = "乌云"
        elif "跌打" in action or "药" in action:
            item, cost, favor, grudge = "一瓶跌打酒", 6, 4, -3
            target = "阿福" if target == "客栈" else target
        elif "酒" in action or "喝一杯" in action:
            item, cost, favor, grudge = "一壶酒", 8, 5, -4
        elif "住店" in action or "开一间" in action:
            item, cost, favor, grudge = "一晚客房", 3, 1, 0
            target = "客栈"
        elif "赏" in action or "打赏" in action:
            item, cost, favor, grudge = "一份赏钱", 5, 4, -2
        else:
            item, cost, favor, grudge = "一壶热茶", 3, 2, -1
        return {
            "item": item,
            "cost": cost,
            "favor": favor,
            "grudge": grudge,
            "target": target,
            "silver": silver,
            "affordable": silver >= cost,
        }

    def _outcome(
        self,
        action: str,
        intent: str,
        target: str,
        severity: int,
        success: bool,
        caught: bool,
        card: dict[str, Any] | None,
        state: dict[str, Any] | None = None,
    ) -> str:
        phrase = clean_action_phrase(action)
        card_hint = f"（{card['title']}也掺和了一脚）" if card else ""
        if intent == "prank":
            if success and caught:
                return f"你{phrase}，手还没收回来，{target}就站在你身后。{card_hint}"
            if success:
                return f"你{phrase}——居然真成了。{target}暂时没发现，但客栈里多了一桩怪事。{card_hint}"
            return f"你{phrase}到一半就露了馅，{target}当场逮住你。{card_hint}"
        if intent == "theft":
            if success and caught:
                return f"你{phrase}，银子刚到手，{target}的算盘珠子突然停了。{card_hint}"
            if success:
                return f"你{phrase}，得手了。{target}还在忙，暂时没顾上盘点。{card_hint}"
            return f"你{phrase}，刚伸手就被{target}按住了手腕。{card_hint}"
        if intent == "fight":
            return f"你{phrase}，和{target}从柜台一直闹到后院，最后被一盆洗菜水浇停。{card_hint}"
        if intent == "help":
            return f"你{phrase}，{target}嘴上不说，手里的活却轻了半分。{card_hint}"
        if intent == "apologize":
            return f"你{phrase}，{target}盯了你半天，把茶碗重重放下，没接话。{card_hint}"
        if intent == "compliment":
            return f"你{phrase}，{target}嘴角动了动，账本上的算珠却拨得慢了一拍。{card_hint}"
        if intent == "probe":
            return f"你{phrase}，{target}压低了声音，只说了半句，就被门外一声马嘶打断。{card_hint}"
        if intent == "buy":
            purchase = self._purchase(action, target, state or {})
            ptarget = purchase["target"]
            if not purchase["affordable"]:
                return (
                    f"你把钱袋翻了个底朝天，只倒出 {purchase['silver']} 两银子，"
                    f"买不起{purchase['item']}。{ptarget}把伸出的手又收了回去。{card_hint}"
                )
            return (
                f"你数出 {purchase['cost']} 两银子，从柜台接过{purchase['item']}，"
                f"递到{ptarget}面前。{ptarget}愣了一下，还是收下了。{card_hint}"
            )
        if intent == "chat":
            if any(word in action for word in ("为什么", "怎么", "吗", "？", "?", "什么")):
                return f"你把问题丢给{target}。{target}停下手里的活，看了你一眼，没有立刻回答。{card_hint}"
            return f"你随口和{target}搭了句话，{target}“嗯”了一声，把抹布往肩上一搭。{card_hint}"
        return f"你{phrase}，{target}“嗯”了一声，把抹布往肩上一搭。{card_hint}"

    def _deltas(
        self,
        action: str,
        intent: str,
        target: str,
        severity: int,
        success: bool,
        caught: bool,
        card: dict[str, Any] | None,
        state: dict[str, Any] | None = None,
    ) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
        delta = {"favor": 0, "grudge": 0, "chaos": 0, "silver": 0, "reputation": 0}
        npc_delta: dict[str, dict[str, int]] = {}

        def add(key: str, value: int) -> None:
            delta[key] = int(delta.get(key, 0)) + int(value)

        def add_npc(key: str, value: int) -> None:
            if target in {"客栈", "客人"}:
                return
            npc_delta.setdefault(target, {})
            npc_delta[target][key] = int(npc_delta[target].get(key, 0)) + int(value)

        if intent == "buy":
            purchase = self._purchase(action, target, state or {})
            if purchase["affordable"]:
                add("silver", -purchase["cost"])
                add("favor", purchase["favor"])
                add("grudge", purchase["grudge"])
                add("reputation", 1)
                if purchase["target"] != "客栈":
                    npc_delta.setdefault(purchase["target"], {})
                    npc_delta[purchase["target"]]["favor"] = (
                        int(npc_delta[purchase["target"]].get("favor", 0)) + purchase["favor"]
                    )
                    npc_delta[purchase["target"]]["grudge"] = (
                        int(npc_delta[purchase["target"]].get("grudge", 0)) + purchase["grudge"]
                    )
            else:
                add("reputation", -1)
        elif intent == "prank":
            if success and caught:
                add("grudge", severity * 2 + 2)
                add("chaos", severity)
                add("favor", -2)
                add("reputation", -1)
                add_npc("grudge", severity * 2 + 2)
            elif success:
                add("chaos", severity)
                add("grudge", 1)
                add("favor", -1)
                add("reputation", 1)
                add_npc("grudge", 1)
            else:
                add("grudge", severity + 2)
                add("chaos", 1)
                add("favor", -1)
                add("reputation", -1)
                add_npc("grudge", severity + 2)
        elif intent == "theft":
            if success:
                add("silver", 2 + severity * 2)
                add("grudge", severity * 2)
                add("chaos", 2)
                add("reputation", -1)
                add_npc("grudge", severity * 2)
            else:
                add("grudge", severity + 1)
                add("reputation", -2)
                add_npc("grudge", severity + 1)
            if caught:
                add("reputation", -1)
                add("grudge", 1)
                add_npc("grudge", 1)
        elif intent == "fight":
            add("grudge", severity * 2)
            add("chaos", severity * 2)
            add("favor", -3)
            add("reputation", -2)
            add_npc("grudge", severity * 2)
        elif intent == "help":
            add("favor", 2 + severity)
            add("reputation", 1)
            add_npc("favor", 2 + severity)
            if any(word in action for word in ("请客", "买单", "送")):
                add("silver", -3)
            elif "帮工" in action or "打扫" in action:
                add("silver", 1)
        elif intent == "apologize":
            add("favor", 2)
            add("grudge", -(3 + severity * 2))
            add("reputation", 1)
            add_npc("grudge", -(4 + severity * 2))
            if "赔" in action:
                add("silver", -2)
        elif intent == "compliment":
            add("favor", 2)
            add("reputation", 1)
            add_npc("favor", 2)
        elif intent == "probe":
            if card and card.get("kind") == "rumor":
                add("reputation", 1)
                add("chaos", 1)
        else:
            add("favor", 1)

        if card:
            effect = card.get("effect") or {}
            negative = intent in {"prank", "theft", "fight"}
            positive = intent in {"help", "apologize", "compliment"}
            for key in ("favor", "grudge", "chaos", "silver", "reputation"):
                if key in effect:
                    value = max(-5, min(5, int(effect.get(key, 0))))
                    # 恶作剧不能因为捡到一张“吉兆卡”反而加好感；
                    # 道歉/帮忙也不应该被一张危险卡反手加记仇。
                    if negative and key in {"favor", "reputation"} and value > 0:
                        continue
                    if positive and key in {"grudge", "chaos"} and value > 0:
                        continue
                    add(key, value)
            for npc, values in (effect.get("npc_favor") or {}).items():
                if npc in {"柳三娘", "阿福", "老周", "乌云", "老陈"}:
                    if negative and int(values) > 0:
                        continue
                    delta["favor"] = int(delta["favor"]) + int(values)
                    npc_delta.setdefault(npc, {})
                    npc_delta[npc]["favor"] = int(npc_delta[npc].get("favor", 0)) + int(values)
            for npc, values in (effect.get("npc_grudge") or {}).items():
                if npc in {"柳三娘", "阿福", "老周", "乌云", "老陈"}:
                    if positive and int(values) > 0:
                        continue
                    delta["grudge"] = int(delta["grudge"]) + int(values)
                    npc_delta.setdefault(npc, {})
                    npc_delta[npc]["grudge"] = int(npc_delta[npc].get("grudge", 0)) + int(values)
        return delta, npc_delta

    def _retaliation(
        self,
        state: dict[str, Any],
        target: str,
        intent: str,
        severity: int,
        turn: int,
    ) -> str | None:
        if intent not in {"prank", "theft", "fight"}:
            return None
        projected = int(state["stats"].get("grudge", 0)) + severity * 2
        if projected < 60:
            return None
        if turn % 2 != 0 and severity < 4:
            return None
        lines = {
            "柳三娘": "柳三娘把一碟桂花糕放在你门口，糕上插着一根鸡毛，旁边压着纸条：“明早自己扫院子。”",
            "阿福": "阿福给你的茶里加了三勺盐，端上来时笑得特别真诚。",
            "老周": "老周在台上把你的糗事编成了新段子，满堂客人笑得拍桌子。",
            "乌云": "乌云把一只死老鼠放在你枕头上，作为回礼。",
            "老陈": "老陈明天还会来，而且这次带了两名差役。",
        }
        return lines.get(target, f"{target}没说话，只是把你的茶碗收走了，换了一只缺口的。")

    def _ending(self, state: dict[str, Any], delta: dict[str, int]) -> tuple[str | None, str]:
        favor = clamp(int(state["stats"].get("favor", 0)) + int(delta.get("favor", 0)))
        grudge = clamp(int(state["stats"].get("grudge", 0)) + int(delta.get("grudge", 0)))
        chaos = clamp(int(state["stats"].get("chaos", 0)) + int(delta.get("chaos", 0)))
        if favor >= 80 and grudge <= 20:
            return "客栈自己人", "编外掌柜"
        if grudge >= 90:
            return "江湖通缉", "头号祸害"
        if chaos >= 80:
            return "客栈重建中", "拆迁办主任"
        if grudge >= 70:
            return None, "头号祸害"
        if favor >= 60:
            return None, "客栈熟人"
        if grudge >= 25:
            return None, "麻烦人物"
        if chaos >= 50:
            return None, "混乱制造者"
        if favor >= 30:
            return None, "熟客"
        if chaos >= 25:
            return None, "不安分"
        if int(state.get("turn", 0)) >= 3:
            return None, "老面孔"
        return None, "初入江湖"

    def _pick_cards(self, action: str, intent: str, target: str) -> list[dict[str, Any]]:
        tags = [target, INTENT_LABELS.get(intent, "")]
        cards = self.store.search_cards(f"{action} {target} {INTENT_LABELS.get(intent, '')}", tags=tags, limit=12)
        # 先按目标收窄：阿福的鞋不应该被“房梁上的燕子窝”抢戏。
        if target not in {"客栈", "客人"}:
            matched = [card for card in cards if target in str(card.get("tags", ""))]
            if matched:
                cards = matched
        preferred = {
            "prank": {"prop", "event"},
            "theft": {"prop", "rumor"},
            "fight": {"prop", "npc", "event"},
            "help": {"remedy", "npc", "event"},
            "apologize": {"remedy", "npc"},
            "compliment": {"remedy", "npc"},
            "probe": {"rumor", "npc", "prop"},
        }.get(intent, {"npc", "prop", "rumor"})

        def score(card: dict[str, Any]) -> float:
            value = float(card.get("score", 0.0))
            if card.get("kind") in preferred:
                value += 1.5
            if target in str(card.get("tags", "")):
                value += 1.0
            if card.get("kind") == "remedy" and intent in {"help", "apologize", "compliment"}:
                value += 2.0
            if card.get("kind") == "remedy" and intent in {"prank", "fight", "theft"}:
                value -= 1.0
            title = str(card.get("title", ""))
            if any(token and token in action for token in (target, "鞋", "账本", "茶壶", "猫", "鱼干", "桂花糕", "伞", "鸡")):
                if any(token in title for token in ("鞋", "账本", "茶壶", "猫", "鱼干", "桂花糕", "伞", "鸡")):
                    value += 1.5
            return value

        cards.sort(key=score, reverse=True)
        return cards[:3]

    # ------------------------------------------------------------------
    # 应用计划
    # ------------------------------------------------------------------
    def _apply_plan(self, state: dict[str, Any], plan: dict[str, Any]) -> None:
        stats = state.setdefault("stats", {})
        for key in ("favor", "grudge", "chaos", "silver", "reputation"):
            stats[key] = int(stats.get(key, 0)) + int(plan.get("deltas", {}).get(key, 0))
        stats["favor"] = clamp(stats["favor"])
        stats["grudge"] = clamp(stats["grudge"])
        stats["chaos"] = clamp(stats["chaos"])
        stats["reputation"] = clamp(stats["reputation"])
        stats["silver"] = max(0, stats["silver"])

        npcs = state.setdefault("npcs", {})
        for npc, values in (plan.get("npc_deltas") or {}).items():
            record = npcs.setdefault(npc, {"favor": 0, "grudge": 0})
            record["favor"] = clamp(int(record.get("favor", 0)) + int(values.get("favor", 0)))
            record["grudge"] = clamp(int(record.get("grudge", 0)) + int(values.get("grudge", 0)))

        state["generation"] = int(plan["generation"])
        state["turn"] = int(plan["turn"])
        state["title"] = plan.get("title") or state.get("title") or "初入江湖"
        state["ending"] = plan.get("ending")
        state["last_scene"] = plan.get("outcome", "")
        state["updated_at"] = utc_now()
        flags = [str(item) for item in state.get("flags", [])]
        for card in plan.get("cards", []):
            effect = card.get("effect") or {}
            tag = effect.get("tag")
            if tag and tag not in flags:
                flags.append(tag)
        state["flags"] = flags[-12:]

    # ------------------------------------------------------------------
    # 文本
    # ------------------------------------------------------------------
    def _scene_brief(self, plan: dict[str, Any], state: dict[str, Any], episodes: list[dict[str, Any]]) -> str:
        lines = [
            f"【本回合】第 {plan['turn']} 回合 · {INTENT_LABELS.get(plan['intent'], plan['intent'])}",
            f"【玩家】{plan['player_id']}",
            f"【行动】{plan['action']}",
            f"【意图】{INTENT_LABELS.get(plan['intent'], plan['intent'])} / 目标：{plan['target']} / 严重度：{plan['severity']}",
        ]
        if plan["intent"] == "status":
            lines.append("【判定】玩家只是想摊开账本看看现状，不改变任何数值。")
        elif plan.get("reset"):
            lines.append("【判定】玩家合上旧账本重新开始；旧一代记忆已被封存，不要回扣旧账。")
        else:
            result = "成功" if plan.get("success") else "失败"
            if plan.get("caught"):
                result += "，而且被当场发现"
            lines.append(f"【判定】{result}。{plan.get('outcome', '')}")
            changes = []
            labels = {"favor": "好感", "grudge": "记仇", "chaos": "混乱", "silver": "银子", "reputation": "名声"}
            for key, value in (plan.get("deltas") or {}).items():
                if value:
                    changes.append(f"{labels.get(key, key)}{value:+d}")
            for npc, values in (plan.get("npc_deltas") or {}).items():
                for key, value in values.items():
                    if value:
                        changes.append(f"{npc}{labels.get(key, key)}{value:+d}")
            lines.append("【数值】" + ("；".join(changes) if changes else "无变化"))
            if plan["intent"] == "chat":
                lines.append("【对话】玩家是在问话/闲聊，不是动手；用 NPC 的反应回应他，可以回扣前情，不要虚构新的数值或道具。")
        if plan.get("retaliation"):
            lines.append(f"【报复】{plan['retaliation']} 必须在正文中写出。")
        if plan.get("ending"):
            lines.append(f"【阶段结局】{plan['ending']}。用一句有仪式感的话收束，但不要结束对话。")
        if plan.get("cards"):
            lines.append("【可用素材】")
            for card in plan["cards"]:
                lines.append(f"- {card['title']}（{card['kind']}）：{card['body']}")
        else:
            lines.append("【可用素材】无特定素材，请用客栈日常细节。")
        if episodes:
            lines.append("【前情记忆】")
            for episode in episodes[-3:]:
                text = str(episode.get("outcome", ""))[:90]
                lines.append(f"- 第{episode.get('turn')}回合：{episode.get('action')} → {text}")
        else:
            lines.append("【前情记忆】这是玩家第一次走进客栈。")
        stats = state.get("stats", {})
        lines.extend(
            [
                "【当前状态】"
                f"好感{stats.get('favor', 0)}，记仇{stats.get('grudge', 0)}，"
                f"混乱{stats.get('chaos', 0)}，银子{stats.get('silver', 0)}两，"
                f"名声{stats.get('reputation', 0)}，称号“{state.get('title', '初入江湖')}”",
                "【写作要求】只写 120-220 字中文正文；严格按判定写成败与报复，不得改数值；"
                + ("必须自然回扣至少一条前情记忆；" if episodes else "这是玩家第一次来，不要编造旧事；")
                + "要有柳三娘/阿福的具体动作或台词；"
                "结尾留一个钩子，但不要提问；不要输出标题、JSON、数值面板或系统提示。",
            ]
        )
        return "\n".join(lines)

    def _status_panel(self, state: dict[str, Any], plan: dict[str, Any]) -> str:
        stats = state.get("stats", {})
        target = plan.get("target", "客栈")
        line = npc_line(target, state)
        title = state.get("title", "初入江湖")
        return (
            f"**第 {state.get('turn', 0)} 回合 · {scene_name(state)}** ｜ 称号：{title}\n\n"
            f"`好感 {stats.get('favor', 0)}` `记仇 {stats.get('grudge', 0)}` "
            f"`混乱 {stats.get('chaos', 0)}` `银子 {stats.get('silver', 0)} 两` "
            f"`名声 {stats.get('reputation', 0)}`\n\n"
            f"> {line}"
        )

    def _reply(
        self,
        story: str,
        state: dict[str, Any],
        plan: dict[str, Any],
        ledger_id: str,
        memory_result: dict[str, Any],
    ) -> str:
        panel = self._status_panel(state, plan)
        ending = plan.get("ending")
        ending_line = f"\n\n🎴 **阶段结局：{ending}**" if ending else ""
        # 存储实现和流水号只留在日志/证据里，不放进玩家看到的正文。
        return f"{story}{ending_line}\n\n---\n{panel}"

    @staticmethod
    def _sanitize_narrative(raw: str | None) -> str:
        text = (raw or "").strip()
        text = re.sub(r"^```(?:markdown|md|text)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        if text.startswith("{") or text.startswith("["):
            return ""
        for prefix in ("旁白：", "旁白:", "正文：", "正文:"):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
        return text[:4000]
