"""sddctx 命令行入口。

命令：
    init      初始化 seekdb、导入工程资料
    import    重新导入（规格更新后使用）
    context   为任务构造开发上下文（规格/代码/测试 + PowerContext 状态）
    state     读取 PowerContext 中保存的任务状态
    run       调用 MiniMax 完成代码修改并验证（见 runner.py）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sddctx import ingest
from sddctx.config import DEMO_APP, EVIDENCE, SAMPLES, ensure_runtime, load_settings
from sddctx.retrieval import build_context, load_task
from sddctx.state import PowerContextClient, PowerContextError
from sddctx.util import write_json


def _settings():
    settings = load_settings()
    ensure_runtime(settings)
    return settings


def _cmd_init(args: argparse.Namespace) -> int:
    settings = _settings()
    materials = ingest.collect_materials(Path(args.demo_app))
    summary = ingest.import_materials(
        materials,
        db_path=settings.db_path,
        evidence_path=EVIDENCE / "import" / "latest.json",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    return _cmd_init(args)


def _context(args: argparse.Namespace):
    settings = _settings()
    task = load_task(args.task)
    state = None
    if not args.no_state:
        client = PowerContextClient(settings.powercontext_url)
        state = client.load_state(settings)
    return build_context(
        task,
        db_path=settings.db_path,
        root=Path(args.demo_app),
        pc_state=state,
    )


def _cmd_context(args: argparse.Namespace) -> int:
    try:
        context = _context(args)
    except PowerContextError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 3
    if args.json:
        write_json(args.json, context)
    print_brief(context)
    return 0


def _cmd_state(args: argparse.Namespace) -> int:
    settings = _settings()
    client = PowerContextClient(settings.powercontext_url)
    try:
        state = client.load_state(settings)
    except PowerContextError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 3
    if args.json:
        write_json(args.json, state)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def _cmd_prompt(args: argparse.Namespace) -> int:
    from sddctx.runner import SYSTEM_PROMPT, _build_prompt, _steps

    settings = _settings()
    task = load_task(args.task)
    client = PowerContextClient(settings.powercontext_url)
    try:
        state = client.load_state(settings)
    except PowerContextError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 3
    if state.get("status") == "empty":
        state = {**state, "pending": _steps(task)}
    context = build_context(task, db_path=settings.db_path, pc_state=state)
    text = f"{SYSTEM_PROMPT}\n\n{_build_prompt(task, context)}\n"
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    write_json(target.with_suffix(".context.json"), context)
    print(f"已生成 Prompt：{target}（可粘贴到 MiniMax 网页版，保存响应后执行 run --response）")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    from sddctx import db

    settings = _settings()
    with db.open_db(settings.db_path) as connection:
        summary = db.stats(connection)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from sddctx.report import ReportError, write_report

    try:
        path = write_report()
    except ReportError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 4
    print(f"已生成开发记录：{path}")
    return 0


def print_brief(context: dict) -> None:
    print(f"任务：{context['task']['task_id']} {context['task']['title']}")
    print(f"查询：{context['db']['query'][:80]}")
    print(f"规格（{len(context['specs'])}）：")
    for item in context["specs"]:
        lines = f"{item['lines'][0]}-{item['lines'][1]}"
        print(f"  - [{item['section_id']}] v{item['version']} {item['path']}:{lines} score={item['score']}")
    print(f"代码（{len(context['code'])}）：")
    for item in context["code"]:
        print(f"  - {item['path']}::{item['symbol']} lines={item['lines'][0]}-{item['lines'][1]}")
    print(f"测试（{len(context['tests'])}）：")
    for item in context["tests"]:
        covers = ",".join(item["covers"]) if item["covers"] else "-"
        print(f"  - [{item['role']}] {item['path']}::{item['symbol']} covers={covers}")
    state = context["state"]
    print(f"状态：{state.get('status')} run_seq={state.get('run_seq')} 来源={state.get('source')}")
    if state.get("completed"):
        print(f"  已完成：{'; '.join(state['completed'])}")
    if state.get("pending"):
        print(f"  待办：{'; '.join(state['pending'])}")
    if state.get("verifications"):
        for verification in state["verifications"]:
            print(
                f"  验证：{verification.get('name')} exit={verification.get('exit_code')} "
                f"passed={verification.get('passed')} failed={verification.get('failed')}"
            )
    print(f"数据库：{context['db']['engine']} {context['db']['version']}")
    for warning in context.get("warnings", []):
        print(f"警告：{warning}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sddctx", description="SDD 工程上下文模块")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("init", "import"):
        command = sub.add_parser(name, help="导入规格/代码/测试到 seekdb")
        command.add_argument("--demo-app", default=str(DEMO_APP))
        command.set_defaults(func=_cmd_init if name == "init" else _cmd_import)

    context = sub.add_parser("context", help="为任务构造开发上下文")
    context.add_argument("--task", default=str(SAMPLES / "TASK-101.json"))
    context.add_argument("--demo-app", default=str(DEMO_APP))
    context.add_argument("--json", default=None, help="把上下文写入指定 JSON 文件")
    context.add_argument("--no-state", action="store_true", help="不读取 PowerContext（仅用于离线调试）")
    context.set_defaults(func=_cmd_context)

    state = sub.add_parser("state", help="读取 PowerContext 任务状态")
    state.add_argument("--json", default=None)
    state.set_defaults(func=_cmd_state)

    report = sub.add_parser("report", help="从运行证据生成 MiniMax 开发记录")
    report.set_defaults(func=_cmd_report)

    stats = sub.add_parser("stats", help="查看 seekdb 资料库统计与索引")
    stats.set_defaults(func=_cmd_stats)

    prompt = sub.add_parser("prompt", help="导出 MiniMax Prompt（网页版手工调用）")
    prompt.add_argument("--task", default=str(SAMPLES / "TASK-101.json"))
    prompt.add_argument("--out", default="evidence/minimax/PROMPT.md")
    prompt.set_defaults(func=_cmd_prompt)

    from sddctx.runner import add_run_parser

    add_run_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
