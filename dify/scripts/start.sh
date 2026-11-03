#!/usr/bin/env bash
# 启动 PowerContext + 客栈后端。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

bash "$GRUDGE_INN_ROOT/scripts/start_powercontext.sh"
for _ in $(seq 1 10); do
  if curl -sf -m 2 "$GRUDGE_INN_POWERCONTEXT_URL/health/ready" > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done
if ! curl -sf -m 2 "$GRUDGE_INN_POWERCONTEXT_URL/health/ready" > /dev/null 2>&1; then
  echo "PowerContext 未就绪，重试启动一次" >&2
  bash "$GRUDGE_INN_ROOT/scripts/start_powercontext.sh"
fi

if curl -sf -m 2 "http://127.0.0.1:$GRUDGE_INN_PORT/health" > /dev/null 2>&1; then
  echo "客栈后端已在运行：http://127.0.0.1:$GRUDGE_INN_PORT"
  exit 0
fi

cd "$GRUDGE_INN_ROOT"
setsid nohup "$PYTHON" -m app.server > "$GRUDGE_INN_RUNTIME/service.log" 2>&1 < /dev/null &
echo "$!" > "$GRUDGE_INN_RUNTIME/service.pid"

for _ in $(seq 1 30); do
  sleep 1
  if curl -sf -m 2 "http://127.0.0.1:$GRUDGE_INN_PORT/health" > /dev/null 2>&1; then
    echo "客栈后端就绪：http://127.0.0.1:$GRUDGE_INN_PORT"
    exit 0
  fi
done
echo "客栈后端启动超时，日志：$GRUDGE_INN_RUNTIME/service.log" >&2
tail -30 "$GRUDGE_INN_RUNTIME/service.log" >&2 || true
exit 1
