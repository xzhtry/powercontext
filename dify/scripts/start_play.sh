#!/usr/bin/env bash
# 可选：启动沉浸式网页入口（8790），把浏览器请求代理到 Dify Service API。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

if [ ! -f "$HOME/.local/share/grudge-inn/dify-app.json" ]; then
  echo "还没生成 Dify API Key。先启动 Dify 并执行：python scripts/bootstrap_dify.py" >&2
  exit 1
fi

if curl -sf -m 2 "http://127.0.0.1:${GRUDGE_INN_PLAY_PORT:-8790}/api/health" > /dev/null 2>&1; then
  echo "网页入口已在运行：http://127.0.0.1:${GRUDGE_INN_PLAY_PORT:-8790}"
  exit 0
fi

cd "$GRUDGE_INN_ROOT"
setsid nohup "$PYTHON" -m app.play > "$GRUDGE_INN_RUNTIME/play.log" 2>&1 < /dev/null &
echo "$!" > "$GRUDGE_INN_RUNTIME/play.pid"

for _ in $(seq 1 20); do
  sleep 1
  if curl -sf -m 2 "http://127.0.0.1:${GRUDGE_INN_PLAY_PORT:-8790}/api/health" > /dev/null 2>&1; then
    echo "网页入口就绪：http://127.0.0.1:${GRUDGE_INN_PLAY_PORT:-8790}"
    exit 0
  fi
done
echo "网页入口启动超时，日志：$GRUDGE_INN_RUNTIME/play.log" >&2
tail -20 "$GRUDGE_INN_RUNTIME/play.log" >&2 || true
exit 1
