"""本地“说书人”模型端点（OpenAI Chat Completions 兼容）。

它有两个作用：
1. 让 Dify 的 LLM 节点在没有任何外部模型 Key 的机器上也能跑通完整流程；
2. 作为真实模型（Ollama / OpenAI-compatible）不可用时的降级方案。

它不是要替代大模型：正式体验时把 Dify 的模型改成 Ollama/Qwen 或任意
OpenAI-compatible 模型即可，DSL 中的 Prompt 不需要改。
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any


def _between(text: str, start: str, end: str) -> str:
    pattern = re.escape(start) + r"(.*?)" + re.escape(end)
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else ""


def _clean(text: str) -> str:
    text = re.sub(r"（[^）]*也掺和了一脚）", "", text)
    text = re.sub(r"^[：:，,\s]+", "", text)
    text = text.replace("成功，而且被当场发现。", "")
    text = text.replace("失败，而且被当场发现。", "")
    text = text.replace("成功。", "").replace("失败。", "")
    text = re.sub(r"^(成功|失败)[，,]\s*", "", text)
    text = re.sub(r"^(我|俺|本大爷|本姑娘)", "", text.strip())
    return text.strip()


def _pick(options: list[str], seed: str) -> str:
    index = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % len(options)
    return options[index]


def _parse_brief(prompt: str) -> dict[str, Any]:
    brief = prompt
    marker = "【本回合场景简报】"
    if marker in brief:
        # 系统提示里也提到了这个标记，真正的简报在最后一次出现之后。
        brief = brief.rsplit(marker, 1)[1]
    action = _between(brief, "【行动】", "【意图】")
    intent_line = _between(brief, "【意图】", "【判定】")
    judge = _between(brief, "【判定】", "【数值】")
    if not judge:
        judge = _between(brief, "【判定】", "【可用素材】")
    target_match = re.search(r"目标：([^\s/]+)", intent_line)
    target = target_match.group(1) if target_match else "柳三娘"
    intent = intent_line.split("/")[0].strip() if intent_line else "闲聊"
    retaliation = _between(brief, "【报复】", "【阶段结局】") or _between(brief, "【报复】", "【可用素材】")
    ending = _between(brief, "【阶段结局】", "【可用素材】")
    materials = _between(brief, "【可用素材】", "【前情记忆】")
    memory = _between(brief, "【前情记忆】", "【当前状态】")
    status = _between(brief, "【当前状态】", "【写作要求】")
    turn_match = re.search(r"第\s*(\d+)\s*回合", brief)
    turn = int(turn_match.group(1)) if turn_match else 1
    grudge_match = re.search(r"记仇\s*(\d+)", status)
    grudge = int(grudge_match.group(1)) if grudge_match else 0
    return {
        "action": action,
        "intent": intent,
        "target": target,
        "judge": judge,
        "retaliation": retaliation,
        "ending": ending,
        "materials": materials,
        "memory": memory,
        "status": status,
        "turn": turn,
        "grudge": grudge,
        "brief": brief,
    }


def _npc_beat(target: str, grudge: int, seed: str) -> str:
    if target == "阿福":
        if grudge >= 40:
            return _pick(
                [
                    "阿福把抹布往肩上一甩，笑得比哭还难看：“客官，您的鞋，自己上房梁取？”",
                    "阿福低头看了看自己光着的脚，又看了看你，默默把菜刀挪到了身后。",
                ],
                seed,
            )
        return _pick(
            [
                "阿福挠了挠后脑勺，把茶碗往你面前推了推：“先喝口热的，别让三娘看见。”",
                "阿福一边擦桌子一边偷瞄你，嘴角憋着笑。",
            ],
            seed,
        )
    if target == "老周":
        return _pick(
            [
                "老周把醒木一拍，拖长了调子：“各位看官，今儿这段，叫《客官与房梁》。”",
                "老周摇着折扇，眼睛却从扇子边上瞟你，分明在记词。",
            ],
            seed,
        )
    if target == "乌云":
        return _pick(
            [
                "乌云从账本上抬起头，尾巴尖那撮白毛抖了抖，像在给你记账。",
                "乌云慢悠悠地绕着你转了一圈，最后把屁股对准了你。",
            ],
            seed,
        )
    if target == "老陈":
        return _pick(
            [
                "老陈把腰牌往桌上一拍，面汤溅出来两滴：“最近，客栈不太平啊。”",
                "老陈眯起眼，手指在桌面上敲了三下，像在数你的罪状。",
            ],
            seed,
        )
    if grudge >= 50:
        return _pick(
            [
                "柳三娘从柜台后抬起眼，茶碗重重一放：“客官，您的茶——我特意多加了三勺盐。”",
                "柳三娘没说话，只把算盘拨得噼啪响，最后一颗珠子停在你名字上。",
            ],
            seed,
        )
    return _pick(
        [
            "柳三娘把抹布往柜台上一搭，嘴角似笑非笑：“客官，住店还是打尖？”",
            "柳三娘头也不抬，算盘珠子却慢了一拍：“账，我记着呢。”",
        ],
        seed,
    )


def _hook(target: str, turn: int, seed: str) -> str:
    hooks = [
        "门外忽然传来一声马嘶，紧接着有人喊你的名字。",
        "后厨的灯“噗”地灭了，黑暗里传来一声很轻的笑。",
        "柜台底下，有什么东西用指甲刮了刮木板。",
        "楼上的房门无风自开，露出一线昏黄的光。",
        "柳三娘忽然把账本合上，说：“今晚，别住西厢。”",
        "屋外的雨声停了，可屋檐还在滴水，一滴，两滴，像有人在数数。",
    ]
    if target == "阿福":
        hooks.append("阿福忽然追出来，手里举着一只鞋：“客官，您落东西了。”")
    if target == "乌云":
        hooks.append("乌云跳上房梁，叼下来一样东西，轻轻放在你脚边。")
    return _pick(hooks, f"{seed}-{turn}")


def narrate_from_prompt(prompt: str) -> str:
    data = _parse_brief(prompt)
    action = _clean(data["action"])
    judge = _clean(data["judge"])
    target = data["target"]
    turn = data["turn"]
    seed = f"{turn}|{action}|{target}"

    if "看状态" in data["intent"] or "看状态" in action:
        return (
            "你把账本拖到灯下，纸页上全是油星和旧茶渍。柳三娘在柜台后拨着算盘，"
            "阿福伸长了脖子偷看，乌云干脆一屁股坐在“欠”字上。你这一路留下的烂账、"
            "人情和怪事，都还在，一笔没少。合上账本时，你听见后厨传来一声轻笑——"
            "像是有人也在翻同一本账。"
        )

    if "重开" in data["intent"] or action.strip() in {"/reset", "重置", "重开"}:
        return (
            "门轴“吱呀”一声，你重新推开客栈的门。大堂还是那张大堂，柜台还是那个柜台，"
            "柳三娘抬眼看了看你，像第一次见，又像什么都记得。阿福端着茶从你身边挤过去，"
            "小声嘟囔：“这位客官，看着眼熟。”你刚坐下，就发现桌角刻着一行小字："
            "“欢迎回来，这次别再藏鞋了。”"
        )

    opening = _pick(
        [
            "油灯把大堂照得半明半暗，柜台上的算盘声忽然停了。",
            "窗外雨丝斜斜地打进来，堂里只剩茶碗碰桌的轻响。",
            "客栈里正热闹，划拳声、锅铲声和猫叫混成一团。",
            "一阵穿堂风把门吹开，灯芯“噼啪”炸了个小火花。",
        ],
        seed,
    )
    beat = _npc_beat(target, data["grudge"], seed)
    callback = ""
    if data["memory"] and "第一次" not in data["memory"]:
        first = next((line for line in data["memory"].splitlines() if line.startswith("- 第")), "")
        if first:
            match = re.search(r"第(\d+)回合：(.+?)\s*→", first)
            if match:
                act = re.sub(r"^(我|俺|本大爷|本姑娘)", "", match.group(2).strip())
                callback = f"他还记得，第{match.group(1)}回合你{act}。"
            else:
                callback = first.lstrip("- ").replace("→", "，").strip()
                callback = callback[:52] + ("…" if len(callback) > 52 else "")
                callback = f"他还记得：{callback}。"

    material = ""
    first_material = next((line for line in data["materials"].splitlines() if line.startswith("- ")), "")
    if first_material:
        title = first_material[2:].split("（", 1)[0]
        material = f"角落里那只{title}，此刻看起来格外碍眼。"

    retaliate = ""
    if data["retaliation"]:
        retaliate = _clean(data["retaliation"])

    ending = ""
    if data["ending"]:
        ending = f"这一夜过后，江湖上多了一个关于你的说法：{data['ending']}。"

    if judge.startswith("你") or judge.startswith("阿福") or judge.startswith("柳三娘"):
        action_line = judge
    else:
        action_line = f"你{action}。{judge}"
    parts = [opening, action_line, beat]
    if callback:
        parts.append(callback)
    if material:
        parts.append(material)
    if retaliate:
        parts.append(retaliate)
    if ending:
        parts.append(ending)
    parts.append(_hook(target, turn, seed))

    text = "".join(parts)
    text = re.sub(r"\s+", "", text)
    if len(text) > 240:
        text = text[:236].rstrip("，。；、") + "。"
    if len(text) < 120:
        text += "堂里的人都看着你，连乌云都竖起了耳朵。"
    return text


def completion_response(prompt: str, model: str) -> dict[str, Any]:
    content = narrate_from_prompt(prompt)
    return {
        "id": f"chatcmpl-grudge-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": max(1, len(prompt) // 2),
            "completion_tokens": max(1, len(content) // 2),
            "total_tokens": max(2, (len(prompt) + len(content)) // 2),
        },
    }
