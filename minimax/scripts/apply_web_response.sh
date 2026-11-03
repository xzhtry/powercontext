#!/usr/bin/env bash
# 应用 MiniMax 网页版/客户端返回的补丁，并完成后续验证与记录。
# 用法：bash scripts/apply_web_response.sh evidence/minimax/response.md [模型名]
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$ROOT"
RESPONSE="${1:-evidence/minimax/response.md}"
MODEL="${2:-MiniMax-M3.1-Flash}"
if [ ! -f "$RESPONSE" ]; then
  echo "找不到响应文件：$RESPONSE" >&2
  echo "请把 MiniMax 的完整回复（含 \`\`\`diff 代码块）保存到该路径" >&2
  exit 1
fi

bash scripts/reset.sh > /dev/null
bash scripts/start_powercontext.sh > /dev/null
"$PYTHON" -m sddctx.cli init --demo-app snapshots/before > /dev/null
"$PYTHON" -m sddctx.cli run --response "$RESPONSE" --model-name "$MODEL" --apply-demo
"$PYTHON" -m sddctx.cli import > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/context/TASK-101-final.json > /dev/null
"$PYTHON" -m sddctx.cli report
bash scripts/verify_before_after.sh
bash scripts/demo_state_reuse.sh | tail -n 4
echo "完成：MiniMax 回复已应用、测试已运行、状态已写入、开发记录已生成。"
