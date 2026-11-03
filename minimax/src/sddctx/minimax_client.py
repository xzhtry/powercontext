"""MiniMax API 客户端（Anthropic Messages 或 OpenAI Chat Completions 兼容协议）。

同一个 Key 在不同套餐下走不同端点；因此协议、Base URL 与模型都可配置：

- Anthropic 兼容：``MINIMAX_PROTOCOL=anthropic``，默认 ``https://api.minimax.cn/anthropic``
- OpenAI 兼容：``MINIMAX_PROTOCOL=openai``，默认 ``https://api.minimax.cn/v1``
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sddctx.config import PACKAGE_ROOT


class MiniMaxError(RuntimeError):
    """MiniMax 请求失败。"""


def load_env_file(path: Path | None = None) -> None:
    """把 .env 中的键值加载到 os.environ（不覆盖已有变量）。"""

    target = path or (PACKAGE_ROOT / ".env")
    if not target.is_file():
        return
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class MiniMaxConfig:
    protocol: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout: float = 600.0
    effort: str = "low"

    @classmethod
    def from_env(cls) -> "MiniMaxConfig":
        load_env_file()
        protocol = os.environ.get("MINIMAX_PROTOCOL", "anthropic").strip().lower()
        default_base = "https://api.minimax.cn/anthropic" if protocol == "anthropic" else "https://api.minimax.cn/v1"
        return cls(
            protocol=protocol,
            base_url=os.environ.get("MINIMAX_BASE_URL", default_base).rstrip("/"),
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M3.1-Flash"),
            api_key=os.environ.get("MINIMAX_API_KEY", "").strip(),
            effort=os.environ.get("MINIMAX_EFFORT", "low").strip().lower(),
        )

    def require_key(self) -> None:
        if not self.api_key:
            raise MiniMaxError(
                "缺少 MINIMAX_API_KEY。请复制 .env.example 为 .env 并填入 MiniMax Token Plan/API Key。"
            )


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:800]
            last_error = MiniMaxError(f"MiniMax HTTP {error.code}: {detail}")
            if error.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise last_error from error
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            last_error = MiniMaxError(f"MiniMax 网络错误：{error}")
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise last_error from error
    raise last_error or MiniMaxError("MiniMax 请求失败")


def complete(system: str, user: str, config: MiniMaxConfig | None = None) -> dict[str, Any]:
    """发送一次对话请求，返回文本、用量与可记录元数据。"""

    resolved = config or MiniMaxConfig.from_env()
    resolved.require_key()
    started = time.monotonic()
    if resolved.protocol == "anthropic":
        url = f"{resolved.base_url}/v1/messages"
        payload = {
            "model": resolved.model,
            "max_tokens": 8192,
            "system": system,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
            "output_config": {"effort": resolved.effort},
        }
        headers = {
            "x-api-key": resolved.api_key,
            "Authorization": f"Bearer {resolved.api_key}",
            "anthropic-version": "2023-06-01",
        }
        raw = _post_json(url, payload, headers, resolved.timeout)
        text = "".join(block.get("text", "") for block in raw.get("content", []) if block.get("type") == "text")
        usage = raw.get("usage", {})
        if not text:
            raise MiniMaxError(
                "MiniMax 返回了空文本（思考 token 可能占满 max_tokens）。"
                f"stop_reason={raw.get('stop_reason')} usage={usage}"
            )
    elif resolved.protocol == "openai":
        url = f"{resolved.base_url}/chat/completions"
        payload = {
            "model": resolved.model,
            "max_tokens": 8192,
            "reasoning_effort": resolved.effort,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {resolved.api_key}"}
        raw = _post_json(url, payload, headers, resolved.timeout)
        choices = raw.get("choices") or []
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = raw.get("usage", {})
        if not text:
            raise MiniMaxError(f"MiniMax 返回了空文本。finish_reason={choices[0].get('finish_reason') if choices else None} usage={usage}")
    else:
        raise MiniMaxError(f"未知的 MINIMAX_PROTOCOL：{resolved.protocol}")

    return {
        "protocol": resolved.protocol,
        "base_url": resolved.base_url,
        "model": resolved.model,
        "text": text,
        "usage": usage,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "response_id": raw.get("id"),
        "raw_usage": usage,
    }
