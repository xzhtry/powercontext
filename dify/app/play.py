"""可选的沉浸式入口：静态客栈页面 + Dify API 代理。

它不直接访问 seekdb/PowerContext，只把浏览器的请求转给 Dify Service API，
因此不会和 Dify 调用的 8787 后端抢单线程 seekdb 连接。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
APP_FILE = Path.home() / ".local" / "share" / "grudge-inn" / "dify-app.json"
BACKEND = os.getenv("GRUDGE_INN_URL", "http://127.0.0.1:8787").rstrip("/")
DIFY = os.getenv("DIFY_API_URL", "http://127.0.0.1:5001").rstrip("/")
HOST = os.getenv("GRUDGE_INN_PLAY_HOST", "0.0.0.0")
PORT = int(os.getenv("GRUDGE_INN_PLAY_PORT", "8790"))

logger = logging.getLogger("grudge-inn-play")
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


def _read_app() -> dict:
    if not APP_FILE.is_file():
        raise RuntimeError("还没有生成 Dify API Key：先运行 python scripts/bootstrap_dify.py")
    return json.loads(APP_FILE.read_text(encoding="utf-8"))


def _post_json(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: int = 120) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


class Handler(BaseHTTPRequestHandler):
    server_version = "GrudgeInnPlay/0.1"

    def log_message(self, fmt: str, *args) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "dify": DIFY, "backend": BACKEND, "app_ready": APP_FILE.is_file()})
            return
        if path == "/api/state":
            query = urlparse(self.path).query
            player = "demo-player"
            for item in query.split("&"):
                if item.startswith("player_id="):
                    player = item.split("=", 1)[1]
            try:
                request = urllib.request.Request(
                    f"{BACKEND}/v1/state",
                    data=json.dumps({"player_id": player}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=20) as response:
                    self._send(200, response.read(), "application/json; charset=utf-8")
            except Exception as error:
                self._json(503, {"ok": False, "error": str(error)})
            return

        name = "index.html" if path in {"/", ""} else path.lstrip("/")
        target = (WEB / name).resolve()
        if WEB.resolve() not in target.parents and target != WEB.resolve():
            self._send(403, b"forbidden", "text/plain")
            return
        if not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        self._send(200, target.read_bytes(), MIME.get(target.suffix, "application/octet-stream"))

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        payload = self._body()
        try:
            if path == "/api/chat":
                player = str(payload.get("player_id") or "demo-player")[:64]
                query = str(payload.get("query") or "").strip()
                conversation_id = str(payload.get("conversation_id") or "")
                if not query:
                    self._json(400, {"ok": False, "error": "说点什么再推门。"})
                    return
                app = _read_app()
                result = _post_json(
                    f"{DIFY}/v1/chat-messages",
                    {
                        "inputs": {"player_id": player},
                        "query": query,
                        "response_mode": "blocking",
                        "conversation_id": conversation_id,
                        "user": "play-web",
                    },
                    headers={"Authorization": f"Bearer {app['api_key']}"},
                )
                self._json(200, {"ok": True, "answer": result.get("answer", ""), "conversation_id": result.get("conversation_id", "")})
                return
            if path == "/api/reset":
                player = str(payload.get("player_id") or "demo-player")[:64]
                result = _post_json(f"{BACKEND}/v1/reset", {"player_id": player})
                self._json(200, {"ok": True, "result": result})
                return
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            self._json(502, {"ok": False, "error": f"Dify 返回 HTTP {error.code}: {detail}"})
            return
        except Exception as error:
            logger.exception("play request failed")
            self._json(500, {"ok": False, "error": str(error)})
            return
        self._json(404, {"ok": False, "error": "unknown path"})


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stderr)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logger.info("客栈入口：http://127.0.0.1:%s", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
