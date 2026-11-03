"""HTTP 入口：给 Dify 的 HTTP Request 节点调用。

启动：
    python -m app.server
默认监听 0.0.0.0:8787。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.config import DATABASE_PATH, HOST, PORT, POWERCONTEXT_URL, ensure_runtime_dirs
from app.game import GameEngine, clean_player_id
from app.memory import PowerContextClient, PowerContextError
from app.narrator import completion_response
from app.store import Store

logger = logging.getLogger("grudge-inn")
STORE: Store | None = None
ENGINE: GameEngine | None = None


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "GrudgeInn/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    # ------------------------------------------------------------------
    # 基础响应
    # ------------------------------------------------------------------
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Player-Id")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json_bytes(payload), "application/json; charset=utf-8")

    def _text(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/markdown; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    # ------------------------------------------------------------------
    # 读取请求
    # ------------------------------------------------------------------
    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 64 * 1024:
            raise ValueError("请求体过大")
        return self.rfile.read(length) if length else b""

    def _json_body(self, raw: bytes | None = None) -> dict[str, Any]:
        raw = self._body() if raw is None else raw
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _player(self, payload: dict[str, Any] | None = None) -> str:
        header = self.headers.get("X-Player-Id")
        if header:
            return clean_player_id(header)
        if payload:
            return clean_player_id(str(payload.get("player_id") or ""))
        return "demo-player"

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health"}:
            self._health()
            return
        if parsed.path == "/v1/models":
            self._json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "grudge-narrator",
                            "object": "model",
                            "created": 0,
                            "owned_by": "grudge-inn",
                        }
                    ],
                },
            )
            return
        if parsed.path == "/v1/stats":
            self._stats()
            return
        if parsed.path == "/v1/ledger":
            query = parse_qs(parsed.query)
            player = query.get("player_id", [None])[0]
            limit = int(query.get("limit", ["20"])[0])
            self._json(200, {"ok": True, "items": STORE.ledger(clean_player_id(player), limit) if STORE else []})
            return
        self._error(404, "未知路径")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/v1/turn/prepare":
                self._prepare(parsed)
            elif parsed.path == "/v1/turn/commit":
                self._commit(parsed)
            elif parsed.path == "/v1/state":
                raw = self._body()
                payload = self._json_body(raw)
                self._json(200, ENGINE.status(self._player(payload)))
            elif parsed.path == "/v1/reset":
                raw = self._body()
                payload = self._json_body(raw)
                self._json(200, ENGINE.reset(self._player(payload)))
            elif parsed.path == "/v1/chat/completions":
                self._chat_completions()
            else:
                self._error(404, "未知路径")
        except ValueError as error:
            self._error(400, str(error))
        except PowerContextError as error:
            logger.warning("PowerContext unavailable: %s", error)
            self._error(503, str(error))
        except Exception:
            logger.exception("request failed")
            self._error(500, "服务内部错误，请查看 logs/service.log")

    def _prepare(self, parsed) -> None:
        raw = self._body()
        payload = self._json_body(raw)
        player = self._player(payload)
        action = payload.get("action")
        if not action:
            action = raw.decode("utf-8", errors="replace") if raw else ""
        result = ENGINE.prepare(player, str(action))
        query = parse_qs(parsed.query)
        if query.get("format", [""])[0] == "text":
            self._text(200, result["scene_brief"])
        else:
            self._json(200, result)

    def _commit(self, parsed) -> None:
        raw = self._body()
        payload = self._json_body(raw)
        player = self._player(payload)
        narrative = payload.get("narrative")
        if not narrative:
            narrative = raw.decode("utf-8", errors="replace") if raw else ""
        reply = ENGINE.commit(player, str(narrative))
        self._text(200, reply)

    def _chat_completions(self) -> None:
        raw = self._body()
        payload = self._json_body(raw)
        messages = payload.get("messages") or []
        parts: list[str] = []
        for message in messages:
            content = message.get("content") if isinstance(message, dict) else ""
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                parts.extend(str(item.get("text", "")) for item in content if isinstance(item, dict))
        prompt = "\n".join(parts)
        result = completion_response(prompt, str(payload.get("model") or "grudge-narrator"))
        if not payload.get("stream"):
            self._json(200, result)
            return

        content = result["choices"][0]["message"]["content"]
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        base = {
            "id": result["id"],
            "object": "chat.completion.chunk",
            "created": result["created"],
            "model": result["model"],
        }
        first = dict(base)
        first["choices"] = [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]
        last = dict(base)
        last["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
        for chunk in (first, last):
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True

    def _health(self) -> None:
        pc = PowerContextClient(POWERCONTEXT_URL)
        db_stats = STORE.stats() if STORE else {}
        self._json(
            200,
            {
                "ok": True,
                "service": "grudge-inn",
                "powercontext": {"url": POWERCONTEXT_URL, "ready": pc.health()},
                "seekdb": {
                    "ready": bool(db_stats),
                    "version": db_stats.get("version"),
                    "cards": db_stats.get("cards"),
                },
                "endpoints": [
                    "POST /v1/turn/prepare",
                    "POST /v1/turn/commit",
                    "POST /v1/state",
                    "POST /v1/reset",
                    "GET /v1/stats",
                    "GET /v1/ledger",
                ],
            },
        )

    def _stats(self) -> None:
        pc = PowerContextClient(POWERCONTEXT_URL)
        stats = STORE.stats() if STORE else {}
        self._json(
            200,
            {
                "ok": True,
                "seekdb": stats,
                "powercontext": {"url": POWERCONTEXT_URL, "ready": pc.health()},
                "recent_ledger": STORE.ledger(limit=5) if STORE else [],
            },
        )


def main(argv: list[str] | None = None) -> int:
    global STORE, ENGINE
    parser = argparse.ArgumentParser(description="记仇客栈后端")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    ensure_runtime_dirs()
    STORE = Store(DATABASE_PATH)
    ENGINE = GameEngine(STORE, PowerContextClient(POWERCONTEXT_URL))
    # 嵌入式 seekdb 的连接与线程绑定；单线程 HTTPServer 可以避免跨线程复用。
    server = HTTPServer((args.host, args.port), Handler)
    logger.info("记仇客栈后端启动：http://%s:%s", args.host, args.port)
    logger.info("seekdb 卡片：%s；PowerContext：%s", STORE.card_count(), POWERCONTEXT_URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，准备退出")
    finally:
        server.server_close()
        STORE.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
