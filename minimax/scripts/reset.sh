#!/usr/bin/env bash
# 清空本地运行态：PowerContext 数据库、seekdb 数据、任务状态与工作目录。
# 用法：bash scripts/reset.sh [--full]
#   --full 同时删除 evidence 下的运行日志（保留提交用样例说明）。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

case "$SDDCTX_RUNTIME" in
  "" | "/" | "$HOME" | "$HOME/") echo "拒绝删除危险路径：$SDDCTX_RUNTIME" >&2; exit 1 ;;
esac

if [ -f "$SDDCTX_RUNTIME/powercontext.pid" ]; then
  kill "$(cat "$SDDCTX_RUNTIME/powercontext.pid")" 2>/dev/null || true
fi
pkill -f "powercontext server run --env-file $SDDCTX_RUNTIME/powercontext.env" 2>/dev/null || true
sleep 1

rm -rf "$SDDCTX_RUNTIME/powercontext" \
       "$SDDCTX_RUNTIME/seekdb" \
       "$SDDCTX_RUNTIME/state" \
       "$SDDCTX_RUNTIME/work" \
       "$SDDCTX_RUNTIME/powercontext-scope.json" \
       "$SDDCTX_RUNTIME/powercontext.pid" \
       "$SDDCTX_RUNTIME/powercontext.log"

if [ "${1:-}" = "--full" ]; then
  rm -rf "$ROOT/evidence/context" "$ROOT/evidence/runs" "$ROOT/evidence/tests" \
         "$ROOT/evidence/minimax" "$ROOT/evidence/patches" "$ROOT/evidence/import"
fi
echo "已清空运行态：$SDDCTX_RUNTIME"
