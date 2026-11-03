"""把 DSL、模型供应商、API Key 一次性装进本地 Dify。

用法（Dify 已启动、后端 8787 已启动）：
    python scripts/bootstrap_dify.py --dify http://127.0.0.1:5001

默认会创建本地演示账号 demo@grudge.local / GrudgeInn2026!。
这是本地演示账号，不是需要提交的真实凭据。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DSL = ROOT / "dsl" / "grudge-inn.chatflow.yml"
RUNTIME = Path.home() / ".local" / "share" / "grudge-inn"


def request(
    base: str,
    method: str,
    path: str,
    *,
    payload: dict | None = None,
    token: str | None = None,
    timeout: int = 60,
) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"{method} {path} -> HTTP {error.code}: {detail}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dify", default=os.getenv("DIFY_CONSOLE_URL", "http://127.0.0.1:5001"))
    parser.add_argument("--email", default=os.getenv("DIFY_EMAIL", "demo@grudge.local"))
    parser.add_argument("--password", default=os.getenv("DIFY_PASSWORD", "GrudgeInn2026!"))
    parser.add_argument("--name", default=os.getenv("DIFY_NAME", "Grudge Inn Demo"))
    parser.add_argument("--dsl", default=str(DEFAULT_DSL))
    parser.add_argument("--backend-url", default=os.getenv("GRUDGE_INN_BACKEND_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--app-id", default=os.getenv("DIFY_APP_ID", ""))
    parser.add_argument("--skip-model", action="store_true")
    args = parser.parse_args(argv)

    base = args.dify.rstrip("/")
    setup = request(base, "GET", "/console/api/setup")
    if setup.get("step") != "finished":
        print("setup Dify account ...")
        request(
            base,
            "POST",
            "/console/api/setup",
            payload={"email": args.email, "name": args.name, "password": args.password},
        )

    login = request(base, "POST", "/console/api/login", payload={"email": args.email, "password": args.password})
    token = login.get("data", {}).get("access_token")
    if not token:
        raise RuntimeError(f"login failed: {login}")
    print("logged in")

    if not args.skip_model:
        # OpenAI-API-compatible 是 Dify 0.15.x 自带的“自定义模型”供应商。
        # 这里指向本作品后端的 /v1/chat/completions，保证无外部 Key 也能体验。
        print("register grudge-narrator model ...")
        request(
            base,
            "POST",
            "/console/api/workspaces/current/model-providers/openai_api_compatible/models",
            token=token,
            payload={
                "model": "grudge-narrator",
                "model_type": "llm",
                "credentials": {
                    "api_key": "grudge-local",
                    "endpoint_url": f"{args.backend_url.rstrip('/')}/v1",
                    "mode": "chat",
                    "context_size": "8192",
                    "max_tokens_to_sample": "500",
                    "function_calling_type": "no_call",
                    "stream_function_calling": "not_supported",
                    "vision_support": "no_support",
                    "stream_mode_delimiter": "\n\n",
                },
            },
        )

    dsl = Path(args.dsl).read_text(encoding="utf-8")
    print("import DSL ...")
    imported = request(
        base,
        "POST",
        "/console/api/apps/imports",
        token=token,
        payload={"mode": "yaml-content", "yaml_content": dsl, **({"app_id": args.app_id} if args.app_id else {})},
        timeout=120,
    )
    if imported.get("status") != "completed":
        raise RuntimeError(f"import failed: {imported}")
    app_id = imported.get("app_id")
    print("app_id:", app_id)

    print("publish ...")
    request(base, "POST", f"/console/api/apps/{app_id}/workflows/publish", token=token, payload={})

    print("create API key ...")
    key = request(base, "POST", f"/console/api/apps/{app_id}/api-keys", token=token, payload={})
    api_key = key.get("token")
    print("api_key:", api_key)

    RUNTIME.mkdir(parents=True, exist_ok=True)
    record = {
        "dify_console_url": base,
        "app_id": app_id,
        "api_key": api_key,
        "model": "grudge-narrator",
        "backend": "http://127.0.0.1:8787",
    }
    (RUNTIME / "dify-app.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {RUNTIME / 'dify-app.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
