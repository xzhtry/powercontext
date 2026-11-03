"""任务运行器：构造上下文 → MiniMax 生成补丁 → 应用 → 运行测试 → 写回状态。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from sddctx.config import PACKAGE_ROOT, ensure_runtime, load_settings
from sddctx.minimax_client import MiniMaxConfig, MiniMaxError, complete
from sddctx.retrieval import build_context, load_task
from sddctx.state import PowerContextClient, PowerContextError
from sddctx.util import content_hash, utc_now, write_json

BEFORE_SNAPSHOT = PACKAGE_ROOT / "snapshots" / "before"
TARGET_TESTS = "tests/test_min_amount_filter.py"
REGRESSION_TESTS = [
    "tests/test_list_invoices.py",
    "tests/test_pagination.py",
    "tests/test_cli.py",
]

SYSTEM_PROMPT = """你是一名严格的规格驱动开发（SDD）助手。你只能依据用户提供的上下文修改代码。
要求：
1. 只输出 unified diff，放在 ```diff 代码块中；不要输出解释、总结或其它代码块。
2. 路径相对 demo_app 根目录，使用 a/src/... 与 b/src/...。
3. 只允许修改 src/invoicehub/ 下的文件；禁止修改 tests/、specs/、data/。
4. 必须满足上下文中的全部规格条目，并保持既有行为（回归测试）不变。
5. 使用 Python 3.11+，金额使用 decimal.Decimal。"""

OUTPUT_RULES = """输出格式（必须严格遵守）：
```diff
--- a/src/invoicehub/service.py
+++ b/src/invoicehub/service.py
@@ ... @@
```
"""


def _steps(task: dict[str, Any]) -> list[str]:
    steps = task.get("steps") or []
    titles: list[str] = []
    for step in steps:
        titles.append(step["title"] if isinstance(step, dict) else str(step))
    return titles


def _build_prompt(task: dict[str, Any], context: dict[str, Any]) -> str:
    lines: list[str] = ["# 开发任务", f"{task['title']}", task["description"], ""]
    if task.get("acceptance"):
        lines.append("## 验收条件")
        lines.extend(f"- {item}" for item in task["acceptance"])
        lines.append("")
    lines.append("## 必须遵守的规格（来自 seekdb 检索）")
    for spec in context["specs"]:
        text = spec["text"]
        if len(text) > 1600:
            text = text[:1600] + "\n...（已截断）"
        lines.append(f"### [{spec['section_id']}] {spec['title']}（v{spec['version']}，来源 {spec['path']}:{spec['lines'][0]}-{spec['lines'][1]}）")
        lines.append(text)
        lines.append("")
    lines.append("## 需要修改的代码")
    for item in context["code"]:
        snippet = item["snippet"]
        if len(snippet) > 5000:
            snippet = snippet[:5000] + "\n# ...（已截断）"
        lines.append(f"### {item['path']}::{item['symbol']}（行 {item['lines'][0]}-{item['lines'][1]}）")
        lines.append("```python")
        lines.append(snippet)
        lines.append("```")
        lines.append("")
    lines.append("## 用于验证的测试（不得修改）")
    for item in context["tests"]:
        lines.append(f"- [{item['role']}] {item['path']}::{item['symbol']} covers={','.join(item['covers']) or '-'}")
    lines.append("")
    state = context["state"]
    lines.append("## 任务状态（来自 PowerContext）")
    lines.append(f"- 状态：{state.get('status')}（第 {state.get('run_seq')} 次运行）")
    lines.append(f"- 已完成：{'; '.join(state.get('completed') or []) or '无'}")
    lines.append(f"- 待办：{'; '.join(state.get('pending') or []) or '无'}")
    for verification in state.get("verifications") or []:
        lines.append(f"- 已有验证：{verification.get('name')} exit={verification.get('exit_code')}")
    lines.append("")
    lines.append(OUTPUT_RULES)
    return "\n".join(lines)


DIFF_BLOCK_RE = re.compile(r"```(?:diff|patch)?\s*\n(.*?)```", re.DOTALL)


def _normalize_header(line: str, marker: str, prefix: str) -> str:
    path = line[len(marker) :].strip().split("\t")[0].strip().replace("\\", "/")
    if path == "/dev/null":
        return f"{marker} /dev/null"
    for existing in ("a/", "b/"):
        if path.startswith(existing):
            path = path[len(existing) :]
    return f"{marker} {prefix}/{path}"


def normalize_diff(diff: str) -> str:
    """把模型常见的路径写法统一成 a/、b/ 前缀，便于 patch -p1 应用。"""

    lines = diff.replace("\r\n", "\n").splitlines()
    normalized: list[str] = []
    for line in lines:
        if line.startswith("--- "):
            normalized.append(_normalize_header(line, "---", "a"))
        elif line.startswith("+++ "):
            normalized.append(_normalize_header(line, "+++", "b"))
        else:
            normalized.append(line)
    return "\n".join(normalized).strip() + "\n"


def extract_diff(text: str) -> str:
    match = DIFF_BLOCK_RE.search(text)
    candidate = match.group(1) if match else text
    start = candidate.find("--- ")
    if start < 0:
        raise ValueError("MiniMax 输出中没有找到 unified diff")
    diff = candidate[start:].replace("\r\n", "\n").strip() + "\n"
    return normalize_diff(diff)


def validate_diff(diff: str) -> list[str]:
    targets = re.findall(r"^\+\+\+ b/(.+)$", diff, re.MULTILINE)
    if not targets:
        raise ValueError("diff 中没有找到 +++ b/ 目标文件")
    for target in targets:
        if target.startswith("/") or ".." in Path(target).parts:
            raise ValueError(f"非法路径：{target}")
        if not target.startswith("src/invoicehub/"):
            raise ValueError(f"补丁只允许修改 src/invoicehub/，收到：{target}")
    return targets


def _parse_counts(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "errors": 0}
    for key, pattern in (("passed", r"(\d+) passed"), ("failed", r"(\d+) failed"), ("errors", r"(\d+) error")):
        match = re.search(pattern, output)
        if match:
            counts[key] = int(match.group(1))
    return counts


def _run_pytest(workdir: Path, targets: list[str], log_path: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", *targets]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(workdir / "src")
    result = subprocess.run(command, cwd=workdir, env=env, capture_output=True, text=True, timeout=600)
    output = result.stdout + result.stderr
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(f"$ {' '.join(command)}\n\n{output}\n[exit code: {result.returncode}]\n", encoding="utf-8")
    return {
        "command": " ".join(command),
        "exit_code": result.returncode,
        "log": str(log_path.relative_to(PACKAGE_ROOT)),
        **_parse_counts(output),
    }


def _copy_before(destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        BEFORE_SNAPSHOT,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.egg-info"),
    )


def _apply_patch(workdir: Path, patch_text: str, patch_path: Path) -> None:
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text, encoding="utf-8")
    for extra in (["--dry-run"], []):
        command = ["patch", "-p1", "-d", str(workdir), "--batch", "--forward", *extra, "-i", str(patch_path)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"应用补丁失败：{' '.join(command)}\n{result.stdout}{result.stderr}")


def _git_head() -> str:
    """返回代码版本标识。

    优先使用 git commit；在 WSL 的 worktree 中 git 可能因 Windows 路径不可用，
    此时退化为源码内容哈希，仍然能与补丁哈希一起定位到具体代码版本。
    """

    try:
        result = subprocess.run(
            ["git", "-C", str(PACKAGE_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        head = result.stdout.strip()
        if result.returncode == 0 and head:
            return head
    except OSError:
        pass
    digest = hashlib.sha256()
    for path in sorted((PACKAGE_ROOT / "demo_app" / "src").rglob("*.py")):
        digest.update(path.relative_to(PACKAGE_ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return f"src-sha256:{digest.hexdigest()[:16]}"


def _call_minimax(task: dict[str, Any], context: dict[str, Any], evidence_dir: Path, run_id: str) -> tuple[str, dict[str, Any]]:
    config = MiniMaxConfig.from_env()
    system = SYSTEM_PROMPT
    user = _build_prompt(task, context)
    prompt_path = evidence_dir / f"{run_id}.prompt.md"
    prompt_path.write_text(user, encoding="utf-8")
    response = complete(system, user, config)
    record = {
        "run_id": run_id,
        "created_at": utc_now(),
        "task_id": task["task_id"],
        "context_digest": context["db"]["context_digest"],
        "prompt_sha256": content_hash(user),
        "prompt_path": str(prompt_path.relative_to(PACKAGE_ROOT)),
        "model": response["model"],
        "protocol": response["protocol"],
        "base_url": response["base_url"],
        "usage": response["usage"],
        "latency_ms": response["latency_ms"],
        "response_id": response["response_id"],
        "response_text": response["text"],
        "response_sha256": content_hash(response["text"]),
    }
    write_json(evidence_dir / f"{run_id}.json", record)
    return response["text"], record


def _apply_demo_app(workdir: Path) -> None:
    target = PACKAGE_ROOT / "demo_app" / "src" / "invoicehub"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(workdir / "src" / "invoicehub", target)


def run_task(args: argparse.Namespace) -> int:
    settings = load_settings()
    ensure_runtime(settings)
    task = load_task(args.task)
    run_id = f"run-{uuid4().hex[:10]}"
    client = PowerContextClient(settings.powercontext_url)
    try:
        state = client.load_state(settings)
    except PowerContextError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 3
    if state.get("status") == "empty":
        state = {**state, "pending": _steps(task)}

    context = build_context(task, db_path=settings.db_path, pc_state=state)
    context_path = PACKAGE_ROOT / "evidence" / "context" / f"{run_id}.json"
    write_json(context_path, context)
    print(f"上下文：{context_path}（{len(context['specs'])} 规格 / {len(context['code'])} 代码 / {len(context['tests'])} 测试）")

    if args.patch:
        patch_text = Path(args.patch).read_text(encoding="utf-8")
        minimax_record = {"source": "provided-patch", "path": args.patch}
    elif args.response:
        response_text = Path(args.response).read_text(encoding="utf-8")
        prompt_text = _build_prompt(task, context)
        prompt_path = EVIDENCE_MINIMAX / f"{run_id}.prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt_text, encoding="utf-8")
        minimax_record = {
            "source": "manual-minimax-web",
            "model": args.model_name,
            "protocol": "manual",
            "base_url": "MiniMax web chat",
            "created_at": utc_now(),
            "prompt_path": str(prompt_path.relative_to(PACKAGE_ROOT)),
            "prompt_sha256": content_hash(prompt_text),
            "response_text": response_text,
            "response_sha256": content_hash(response_text),
            "usage": None,
            "latency_ms": None,
        }
        write_json(EVIDENCE_MINIMAX / f"{run_id}.json", minimax_record)
        patch_text = extract_diff(response_text)
    else:
        try:
            response_text, minimax_record = _call_minimax(task, context, EVIDENCE_MINIMAX, run_id)
        except MiniMaxError as error:
            print(f"错误：{error}", file=sys.stderr)
            return 4
        patch_text = extract_diff(response_text)
    try:
        targets = validate_diff(patch_text)
    except ValueError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 4

    workdir = settings.work_dir / run_id / "app"
    _copy_before(workdir)
    patch_path = PACKAGE_ROOT / "evidence" / "patches" / f"{run_id}.diff"
    try:
        _apply_patch(workdir, patch_text, patch_path)
    except RuntimeError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 4

    target_result = _run_pytest(workdir, [TARGET_TESTS], PACKAGE_ROOT / "evidence" / "tests" / f"{run_id}-target.log")
    regression_result = _run_pytest(
        workdir, REGRESSION_TESTS, PACKAGE_ROOT / "evidence" / "tests" / f"{run_id}-regression.log"
    )
    full_result = _run_pytest(workdir, [], PACKAGE_ROOT / "evidence" / "tests" / f"{run_id}-full.log")
    success = all(
        result["exit_code"] == 0 and result["failed"] == 0 and result["errors"] == 0
        for result in (target_result, regression_result, full_result)
    )

    verification = [
        {"name": name, **result, "code_version": f"{_git_head()} + patch {content_hash(patch_text)[:12]}"}
        for name, result in (
            ("target", target_result),
            ("regression", regression_result),
            ("full", full_result),
        )
    ]
    completed = list(dict.fromkeys([*(state.get("completed") or []), *_steps(task)])) if success else list(
        state.get("completed") or []
    )
    pending = [] if success else [step for step in _steps(task) if step not in completed]
    next_state = {
        "status": "verified" if success else "failed",
        "completed": completed,
        "pending": pending,
        "verifications": verification,
        "context_digest": context["db"]["context_digest"],
        "patch_sha256": content_hash(patch_text),
        "patch_path": str(patch_path.relative_to(PACKAGE_ROOT)),
        "minimax": {key: minimax_record.get(key) for key in ("model", "protocol", "base_url", "usage", "latency_ms")},
    }
    saved = client.save_state(settings, task["task_id"], next_state)

    if success and args.apply_demo:
        _apply_demo_app(workdir)
        print(f"已把 MiniMax 修改结果写回 demo_app/src/invoicehub（补丁：{patch_path}）")

    summary = {
        "run_id": run_id,
        "task_id": task["task_id"],
        "success": success,
        "patch": str(patch_path.relative_to(PACKAGE_ROOT)),
        "patch_sha256": content_hash(patch_text),
        "context_digest": context["db"]["context_digest"],
        "targets": targets,
        "tests": verification,
        "state": {
            "run_seq": saved.get("run_seq"),
            "status": saved.get("status"),
            "entry": saved.get("entry"),
        },
        "minimax": minimax_record,
        "context": str(context_path.relative_to(PACKAGE_ROOT)),
    }
    write_json(PACKAGE_ROOT / "evidence" / "runs" / f"{run_id}.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if success else 1


EVIDENCE_MINIMAX = PACKAGE_ROOT / "evidence" / "minimax"


def add_run_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser("run", help="调用 MiniMax 修改代码并验证")
    parser.add_argument("--task", default=str(PACKAGE_ROOT / "samples" / "TASK-101.json"))
    parser.add_argument("--patch", default=None, help="使用已有补丁（不调用 MiniMax，用于离线复验）")
    parser.add_argument("--response", default=None, help="使用已保存的 MiniMax 响应文本（网页版手工调用）")
    parser.add_argument("--model-name", default="MiniMax-M3.1-Flash")
    parser.add_argument("--apply-demo", action="store_true", help="验证通过后把结果写回 demo_app/src")
    parser.set_defaults(func=run_task)
