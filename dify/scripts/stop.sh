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
      # 等进程真正退出，避免紧接着的 init 健康检查撞到“还没死透”的旧端口
      for _ in $(seq 1 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.25
      done
      echo "已停止 $name (pid $pid)"
    fi
    rm -f "$pidfile"
  fi
done
pkill -f 'python -m app.server' 2>/dev/null || true
for _ in $(seq 1 20); do
  if ! curl -sf -m 1 "http://127.0.0.1:${GRUDGE_INN_POWERCONTEXT_PORT:-8766}/health/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
