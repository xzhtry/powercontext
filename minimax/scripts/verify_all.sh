#!/usr/bin/env bash
# 一键复验（不需要 MiniMax Key）：
#   reset → init(seekdb, 修改前快照) → context → run --patch → import(修改后) → context
#   → 修改前后测试 → 规格演进 → 状态复用 → 模块测试
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$ROOT"
PATCH="${1:-changes/final-minimax.diff}"
if [ ! -f "$PATCH" ]; then
  echo "补丁不存在：$PATCH" >&2
  exit 1
fi

echo "== 0. 清空运行态并启动 =="
bash scripts/reset.sh > /dev/null
bash scripts/start_powercontext.sh > /dev/null

echo "== 1. 从空状态导入修改前工程资料 =="
"$PYTHON" -m sddctx.cli init --demo-app snapshots/before > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/context/TASK-101-initial.json > /dev/null
echo "   已生成 evidence/context/TASK-101-initial.json"

echo "== 2. 应用补丁并验证，写入 PowerContext =="
"$PYTHON" -m sddctx.cli run --patch "$PATCH" > /dev/null
echo "   已生成 evidence/runs 与 evidence/tests 运行记录"

echo "== 3. 导入修改后工程资料并重新构造上下文 =="
"$PYTHON" -m sddctx.cli import > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/context/TASK-101-final.json > /dev/null
echo "   已生成 evidence/context/TASK-101-final.json"

echo "== 4. 修改前后测试 =="
bash scripts/verify_before_after.sh

echo "== 5. 规格更新后上下文切换 =="
bash scripts/demo_spec_update.sh | tail -n 6

echo "== 6. 任务状态跨重启复用 =="
bash scripts/demo_state_reuse.sh | tail -n 5

echo "== 7. 上下文模块测试 =="
PYTHONPATH=src "$PYTHON" -m pytest -q tests

echo "ALL PASS：离线复验完成。"
