"""用本地 mock HTTP 服务验证 MiniMax 协议拼装与响应解析（不访问真实 API）。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sddctx.minimax_client import MiniMaxConfig, MiniMaxError, complete

CAPTURED: dict = {}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        CAPTURED["path"] = self.path
        CAPTURED["headers"] = dict(self.headers)
        CAPTURED["body"] = body
        if self.path.endswith("/v1/messages"):
            payload = {
                "id": "msg_test",
                "content": [
                    {"type": "thinking", "thinking": "reason"},
                    {"type": "text", "text": "```diff\n--- a/x\n+++ b/x\n```"},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "stop_reason": "end_turn",
            }
        else:
            payload = {
                "id": "chat_test",
                "choices": [{"index": 0, "message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        return


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def _header(name: str) -> str | None:
    for key, value in CAPTURED["headers"].items():
        if key.lower() == name.lower():
            return value
    return None


def test_anthropic_protocol(server):
    config = MiniMaxConfig(
        protocol="anthropic", base_url=server, model="MiniMax-M3.1-Flash", api_key="test-key"
    )
    result = complete("system", "user", config)
    assert result["text"].startswith("```diff")
    assert result["usage"] == {"input_tokens": 10, "output_tokens": 20}
    assert CAPTURED["path"] == "/v1/messages"
    assert _header("x-api-key") == "test-key"
    assert _header("authorization") == "Bearer test-key"
    assert CAPTURED["body"]["output_config"] == {"effort": "low"}
    assert CAPTURED["body"]["max_tokens"] == 8192


def test_openai_protocol(server):
    config = MiniMaxConfig(protocol="openai", base_url=server, model="MiniMax-M3.1-Flash", api_key="test-key")
    result = complete("system", "user", config)
    assert result["text"] == "ok"
    assert CAPTURED["path"] == "/chat/completions"
    assert _header("authorization") == "Bearer test-key"
    assert CAPTURED["body"]["reasoning_effort"] == "low"


def test_missing_key_is_reported(server):
    config = MiniMaxConfig(protocol="anthropic", base_url=server, model="m", api_key="")
    with pytest.raises(MiniMaxError):
        complete("system", "user", config)
