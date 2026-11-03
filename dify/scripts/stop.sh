#!/usr/bin/env bash
# 停止本作品启动的两个服务（不会影响其他 PowerContext/seekdb 实例）。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

for name in play service powercontext; do
  pidfile="$GRUDGE_INN_RUNTIME/$name.pid"
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "已停止 $name (pid $pid)"
    fi
    rm -f "$pidfile"
  fi
done
pkill -f 'python -m app.server' 2>/dev/null || true
