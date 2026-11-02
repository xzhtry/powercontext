#!/usr/bin/env bash
# 真实 MiniMax 调用：生成补丁 → 应用 → 测试 → 写回 demo_app → 重新导入 → 生成开发记录。
# 前置：.env 中配置 MINIMAX_API_KEY（或使用下方手工网页版流程）。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$ROOT"

if [ ! -f .env ]; then
  echo "缺少 .env：请复制 .env.example 为 .env 并填写 MINIMAX_API_KEY" >&2
  exit 1
fi
if ! grep -Eq '^MINIMAX_API_KEY=.+' .env || grep -q '^MINIMAX_API_KEY=replace-me' .env; then
  echo ".env 中的 MINIMAX_API_KEY 为空或仍是占位值" >&2
  echo "可改用网页版：python -m sddctx.cli prompt --out evidence/minimax/PROMPT.md" >&2
  exit 1
fi

bash scripts/start_powercontext.sh > /dev/null
"$PYTHON" -m sddctx.cli run --apply-demo
"$PYTHON" -m sddctx.cli import > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/context/TASK-101-final.json > /dev/null
"$PYTHON" -m sddctx.cli report
bash scripts/verify_before_after.sh
bash scripts/demo_state_reuse.sh | tail -n 4
echo "已完成真实 MiniMax 改码、测试、状态写入与开发记录生成。"
