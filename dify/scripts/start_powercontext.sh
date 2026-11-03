#!/usr/bin/env bash
# 启动本作品专用的 PowerContext Server（SQLite 元数据），端口 8766。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

PC_HOME="$GRUDGE_INN_RUNTIME/powercontext"
mkdir -p "$PC_HOME"
ENV_FILE="$GRUDGE_INN_RUNTIME/powercontext.env"
cat > "$ENV_FILE" <<EOF
POWERCONTEXT_HOME=$PC_HOME
POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
POWERCONTEXT_SERVER_DATABASE_URL=sqlite+aiosqlite:///$PC_HOME/powercontext.db
POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1
POWERCONTEXT_SERVER_HTTP_PORT=$GRUDGE_INN_POWERCONTEXT_PORT
POWERCONTEXT_SERVER_ACCESS_MODE=disabled
POWERCONTEXT_SERVER_MCP_ENABLED=false
POWERCONTEXT_SERVER_DASHBOARD_ENABLED=false
EOF

if curl -sf -m 2 "$GRUDGE_INN_POWERCONTEXT_URL/health/ready" > /dev/null 2>&1; then
  echo "PowerContext 已在运行：$GRUDGE_INN_POWERCONTEXT_URL"
  exit 0
fi

if ! "$PYTHON" -c "import powercontext" > /dev/null 2>&1; then
  echo "缺少 powercontext，请先执行：bash scripts/setup.sh" >&2
  exit 1
fi
if [ ! -x "$PC_BIN" ]; then
  echo "找不到 powercontext 命令：$PC_BIN" >&2
  exit 1
fi

setsid nohup "$PC_BIN" server run --env-file "$ENV_FILE" \
  > "$GRUDGE_INN_RUNTIME/powercontext.log" 2>&1 < /dev/null &
echo "$!" > "$GRUDGE_INN_RUNTIME/powercontext.pid"

for _ in $(seq 1 30); do
  sleep 1
  if curl -sf -m 2 "$GRUDGE_INN_POWERCONTEXT_URL/health/ready" > /dev/null 2>&1; then
    echo "PowerContext 就绪：$GRUDGE_INN_POWERCONTEXT_URL"
    exit 0
  fi
done
echo "PowerContext 启动超时，日志：$GRUDGE_INN_RUNTIME/powercontext.log" >&2
tail -30 "$GRUDGE_INN_RUNTIME/powercontext.log" >&2 || true
exit 1
