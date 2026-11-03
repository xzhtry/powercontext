#!/usr/bin/env bash
# 重置一个玩家，或清空本作品的整个运行态。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

if [ "${1:-}" = "--hard" ]; then
  bash "$GRUDGE_INN_ROOT/scripts/stop.sh" || true
  case "$GRUDGE_INN_RUNTIME" in
    *grudge-inn*)
      rm -rf "$GRUDGE_INN_RUNTIME"
      echo "已清空运行态：$GRUDGE_INN_RUNTIME"
      echo "重新初始化：bash scripts/init.sh"
      ;;
    *)
      echo "拒绝删除非 grudge-inn 目录：$GRUDGE_INN_RUNTIME" >&2
      exit 1
      ;;
  esac
  exit 0
fi

PLAYER="${1:-demo-player}"
curl -s -X POST "http://127.0.0.1:$GRUDGE_INN_PORT/v1/reset" \
  -H 'Content-Type: application/json' \
  -d "{\"player_id\":\"$PLAYER\"}"
echo
echo "已重置玩家：$PLAYER（旧记忆保留为上一代，不会污染新局）"
