"""从运行证据生成 MiniMax 开发记录。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sddctx.config import EVIDENCE, PACKAGE_ROOT
from sddctx.util import read_json, utc_now, write_json


class ReportError(RuntimeError):
    pass


def _latest_run() -> dict[str, Any]:
    runs = sorted((EVIDENCE / "runs").glob("*.json"), key=lambda path: path.stat().st_mtime)
    if not runs:
        raise ReportError("没有运行记录；请先执行 sddctx run")
    for path in reversed(runs):
        summary = read_json(path)
        if summary.get("minimax", {}).get("model"):
            return summary
    raise ReportError("最近的运行没有 MiniMax 记录（可能使用了 --patch）。请先配置 .env 并执行 sddctx run")


def _diff_stats(patch: Path) -> tuple[int, int]:
    added = removed = 0
    for line in patch.read_text(encoding="utf-8").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def build_record() -> str:
    summary = _latest_run()
    run_id = summary["run_id"]
    minimax = summary["minimax"]
    record_path = EVIDENCE / "minimax" / f"{run_id}.json"
    record = read_json(record_path) if record_path.is_file() else {}
    patch = PACKAGE_ROOT / summary["patch"]
    added, removed = _diff_stats(patch)
    tests = summary["tests"]
    all_ok = all(item["exit_code"] == 0 and item["failed"] == 0 for item in tests)

    lines = [
        "# MiniMax 开发记录",
        "",
        f"- 生成时间：{record.get('created_at', utc_now())}",
        f"- 任务：{summary['task_id']}（上下文摘要 `{summary['context_digest']}`）",
        f"- 调用方式：`{record.get('source', 'api')}`",
        f"- 模型：`{minimax.get('model')}`，协议：`{minimax.get('protocol')}`，端点：`{minimax.get('base_url')}`",
        f"- 用量：`{json.dumps(minimax.get('usage'), ensure_ascii=False)}`，时延：{minimax.get('latency_ms')} ms",
        f"- Prompt：`{record.get('prompt_path')}`（sha256 `{str(record.get('prompt_sha256'))[:16]}…`）",
        f"- 响应：sha256 `{str(record.get('response_sha256'))[:16]}…`，response id `{record.get('response_id')}`",
        f"- 补丁：`{summary['patch']}`（+{added} / -{removed} 行，sha256 `{summary.get('patch_sha256', '')[:16]}`）",
        "",
        "## 提供的上下文",
        "",
        f"见 `{summary['context']}`。模型只看到检索得到的规格、代码符号、测试清单与 PowerContext 状态：",
        "",
        "| 类别 | 条目 |",
        "| --- | --- |",
    ]
    context = read_json(PACKAGE_ROOT / summary["context"])
    lines.append("| 规格 | " + "<br>".join(f"`{item['section_id']}` v{item['version']}" for item in context["specs"]) + " |")
    lines.append("| 代码 | " + "<br>".join(f"`{item['path']}::{item['symbol']}`" for item in context["code"]) + " |")
    lines.append(
        "| 测试 | "
        + "<br>".join(f"`{item['path']}::{item['symbol']}`" for item in context["tests"])
        + " |"
    )
    lines += [
        "",
        "## 代码修改过程",
        "",
        "1. `sddctx run` 调用 MiniMax，要求只输出 unified diff，且只修改 `src/invoicehub/`。",
        "2. 补丁先做路径校验，再在 `snapshots/before` 的副本上 dry-run / 应用。",
        "3. 依次运行目标测试、回归测试、全量测试；全部通过才写回 `demo_app/src`。",
        "",
        "## 验证结果",
        "",
        "| 套件 | 命令 | 退出码 | 通过 | 失败 | 日志 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in tests:
        lines.append(
            f"| {item['name']} | `{item['command']}` | {item['exit_code']} | {item['passed']} | {item['failed']} | `{item['log']}` |"
        )
    if record.get("source") == "manual-minimax-web":
        repro = [
            "bash scripts/make_prompt.sh",
            "# 把 evidence/minimax/PROMPT.md 发给 MiniMax，保存回复为 evidence/minimax/response.md",
            "bash scripts/apply_web_response.sh evidence/minimax/response.md \"MiniMax web (model not specified)\"",
            "python -m sddctx.cli report",
        ]
    else:
        repro = [
            "cp .env.example .env   # 填 MINIMAX_API_KEY",
            "python -m sddctx.cli run --apply-demo",
            "python -m sddctx.cli import",
            "python -m sddctx.cli report",
        ]
    lines += [
        "",
        f"结论：{'全部通过' if all_ok else '存在失败'}。",
        "",
        "## 状态写入",
        "",
        f"- PowerContext `run_seq={summary['state']['run_seq']}`，状态 `{summary['state']['status']}`，"
        f"artifact `{summary['state']['entry']}`。",
        "- 读取方式：`python -m sddctx.cli state`；读取后的状态会进入下一次 `context.state`。",
        "",
        "## 复现",
        "",
        "```bash",
        *repro,
        "```",
        "",
        "> 模型响应全文保存在 `evidence/minimax/`，Prompt 全文保存在同一目录的 `.prompt.md`；"
        "本记录不包含 API Key。",
    ]
    return "\n".join(lines) + "\n"


def write_report() -> Path:
    content = build_record()
    target = PACKAGE_ROOT / "docs" / "minimax-dev-record.md"
    target.write_text(content, encoding="utf-8")
    write_json(EVIDENCE / "minimax" / "record-index.json", {"generated_at": utc_now(), "path": str(target)})
    return target
