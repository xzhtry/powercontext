#!/usr/bin/env bash
# 为“修改前”代码准备一段可粘贴到 MiniMax 网页版/客户端的 Prompt。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$ROOT"
bash scripts/start_powercontext.sh > /dev/null
"$PYTHON" -m sddctx.cli init --demo-app snapshots/before > /dev/null
"$PYTHON" -m sddctx.cli prompt --out evidence/minimax/PROMPT.md
echo "把 evidence/minimax/PROMPT.md 全文发给 MiniMax，保存回复为 evidence/minimax/response.md"
echo "然后执行：python -m sddctx.cli run --response evidence/minimax/response.md --apply-demo"
