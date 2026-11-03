"""生成 Dify 0.15.x Chatflow DSL。

用法：
    python scripts/build_dsl.py
输出：
    dsl/grudge-inn.chatflow.yml
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dsl" / "grudge-inn.chatflow.yml"

SYSTEM_PROMPT = """你是《记仇客栈》的说书人，用中文第二人称写一段互动小说。

你会收到一份【本回合场景简报】。其中的成败、数值、NPC 态度、报复和阶段结局都是已经发生的“事实”，你不能改写，也不能用“也许”“似乎”来推翻。

写作规则：
1. 只写 120-220 字正文，不要标题、列表、JSON、数值面板、系统提示或解释。
2. 必须写出目标 NPC 的具体动作或一句台词。柳三娘嘴毒心软，阿福憨直记仇，乌云是只黑猫。
3. 有【前情记忆】时，自然回扣至少一个旧梗，让玩家感到“它真的记得”；没有前情时写初次见面。
4. 有【报复】时，必须在正文里发生；有【阶段结局】时，用一句有仪式感的话收束，但不要结束对话。
5. 结尾留一个让人想继续玩的钩子，但不要向玩家提问。
6. 基调：江湖、烟火气、好笑但不低俗；不要解释规则，不要跳出角色。"""

USER_PROMPT = """【本回合场景简报】
{{#prepare.body#}}

请直接写正文。"""


def node(node_id: str, node_type: str, title: str, x: int, y: int, data: dict) -> dict:
    payload = {"type": node_type, "title": title, "desc": "", "selected": False}
    payload.update(data)
    return {
        "id": node_id,
        "type": "custom",
        "position": {"x": x, "y": y},
        "positionAbsolute": {"x": x, "y": y},
        "width": 244,
        "height": 100,
        "selected": False,
        "sourcePosition": "right",
        "targetPosition": "left",
        "data": payload,
    }


def edge(source: str, target: str, source_type: str, target_type: str) -> dict:
    return {
        "id": f"{source}-{target}",
        "source": source,
        "sourceHandle": "source",
        "target": target,
        "targetHandle": "target",
        "type": "custom",
        "data": {"isInIteration": False, "sourceType": source_type, "targetType": target_type},
    }


def build() -> dict:
    start = node(
        "start",
        "start",
        "开始 · 报上名号",
        80,
        260,
        {
            "variables": [
                {
                    "type": "text-input",
                    "label": "玩家名号（用于跨会话记忆）",
                    "variable": "player_id",
                    "required": False,
                    "max_length": 64,
                    "default": "demo-player",
                    "hint": "同一个名号 = 同一个会被记仇的江湖人",
                }
            ]
        },
    )
    prepare = node(
        "prepare",
        "http-request",
        "1. 读记忆 + 检索江湖卡",
        360,
        260,
        {
            "method": "post",
            "url": "http://127.0.0.1:8787/v1/turn/prepare?format=text",
            "authorization": {"type": "no-auth", "config": None},
            "headers": "Content-Type: text/plain; charset=utf-8\nX-Player-Id: {{#start.player_id#}}",
            "params": "",
            "body": {
                "type": "raw-text",
                "data": [{"key": "", "type": "text", "value": "{{#sys.query#}}"}],
            },
            "timeout": {"max_connect_timeout": 10, "max_read_timeout": 30, "max_write_timeout": 10},
            "retry_config": {"retry_enabled": False, "max_retries": 0, "retry_interval": 100},
            "variables": [],
        },
    )
    narrate = node(
        "narrate",
        "llm",
        "2. 说书人写场景",
        640,
        260,
        {
            "model": {
                "provider": "openai_api_compatible",
                "name": "grudge-narrator",
                "mode": "chat",
                "completion_params": {"temperature": 0.85, "max_tokens": 500},
            },
            "prompt_template": [
                {"role": "system", "text": SYSTEM_PROMPT},
                {"role": "user", "text": USER_PROMPT},
            ],
            "context": {"enabled": False, "variable_selector": []},
            "vision": {"enabled": False},
            "memory": {
                "window": {"enabled": False, "size": 10},
                "role_prefix": {"user": "", "assistant": ""},
            },
            "variables": [],
        },
    )
    commit = node(
        "commit",
        "http-request",
        "3. 落账 + 写记忆",
        920,
        260,
        {
            "method": "post",
            "url": "http://127.0.0.1:8787/v1/turn/commit",
            "authorization": {"type": "no-auth", "config": None},
            "headers": "Content-Type: text/plain; charset=utf-8\nX-Player-Id: {{#start.player_id#}}",
            "params": "",
            "body": {
                "type": "raw-text",
                "data": [{"key": "", "type": "text", "value": "{{#narrate.text#}}"}],
            },
            "timeout": {"max_connect_timeout": 10, "max_read_timeout": 30, "max_write_timeout": 10},
            "retry_config": {"retry_enabled": False, "max_retries": 0, "retry_interval": 100},
            "variables": [],
        },
    )
    answer = node(
        "answer",
        "answer",
        "4. 把这一页给你看",
        1200,
        260,
        {"answer": "{{#commit.body#}}", "variables": []},
    )

    return {
        "version": "0.1.5",
        "kind": "app",
        "app": {
            "name": "记仇客栈 · Grudge Inn",
            "mode": "advanced-chat",
            "icon": "🏮",
            "icon_background": "#FFF3E0",
            "description": "你负责捣蛋，AI 负责记仇。一个会用 seekdb 检索江湖素材、用 PowerContext 跨会话记住你恶作剧的互动客栈。",
            "use_icon_as_answer_icon": False,
        },
        "workflow": {
            "graph": {
                "nodes": [start, prepare, narrate, commit, answer],
                "edges": [
                    edge("start", "prepare", "start", "http-request"),
                    edge("prepare", "narrate", "http-request", "llm"),
                    edge("narrate", "commit", "llm", "http-request"),
                    edge("commit", "answer", "http-request", "answer"),
                ],
                "viewport": {"x": 0, "y": 0, "zoom": 0.85},
            },
            "features": {
                "file_upload": {
                    "enabled": False,
                    "allowed_file_types": ["image"],
                    "allowed_file_extensions": [".jpg", ".jpeg", ".png", ".webp"],
                    "allowed_file_upload_methods": ["local_file", "remote_url"],
                    "number_limits": 3,
                    "image": {"enabled": False, "number_limits": 3, "transfer_methods": ["local_file", "remote_url"]},
                },
                "opening_statement": (
                    "**欢迎来到记仇客栈。**\n\n"
                    "你负责捣蛋，AI 负责记仇。\n\n"
                    "这里的每一笔账，都会跨会话记住：你藏过谁的鞋、往谁的茶里加过盐、又欠了谁一句道歉。\n\n"
                    "报上名号，推门吧。"
                ),
                "suggested_questions": [
                    "我把阿福的鞋藏到房梁上",
                    "给柳三娘送一碟桂花糕，夸她年轻",
                    "偷偷翻开柜台的账本",
                    "我回来了，柳三娘还记不记得我",
                ],
                "suggested_questions_after_answer": {"enabled": False},
                "retriever_resource": {"enabled": False},
                "sensitive_word_avoidance": {"enabled": False},
                "speech_to_text": {"enabled": False},
                "text_to_speech": {"enabled": False, "language": "", "voice": ""},
            },
            "environment_variables": [],
            "conversation_variables": [],
        },
    }


def _replace_hosts(value, old: str, new: str):
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_hosts(item, old, new) for item in value]
    if isinstance(value, dict):
        return {key: _replace_hosts(item, old, new) for key, item in value.items()}
    return value


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    OUT.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    docker_data = _replace_hosts(data, "http://127.0.0.1:8787", "http://host.docker.internal:8787")
    docker_out = OUT.with_name("grudge-inn.chatflow.docker.yml")
    docker_out.write_text(
        yaml.safe_dump(docker_data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"wrote {docker_out} ({docker_out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
