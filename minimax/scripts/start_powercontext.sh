#!/usr/bin/env bash
# 启动 PowerContext Server（SQLite 存储），供 sddctx 保存/读取任务状态。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

mkdir -p "$SDDCTX_RUNTIME/powercontext"
ENV_FILE="$SDDCTX_RUNTIME/powercontext.env"
cat > "$ENV_FILE" <<EOF
POWERCONTEXT_HOME=$SDDCTX_RUNTIME/powercontext
POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
POWERCONTEXT_SERVER_DATABASE_URL=sqlite+aiosqlite:///$SDDCTX_RUNTIME/powercontext/powercontext.db
POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1
POWERCONTEXT_SERVER_HTTP_PORT=8765
POWERCONTEXT_SERVER_ACCESS_MODE=disabled
POWERCONTEXT_SERVER_MCP_ENABLED=false
POWERCONTEXT_SERVER_DASHBOARD_ENABLED=false
EOF

if curl -sf -m 2 "$POWERCONTEXT_URL/health/ready" > /dev/null 2>&1; then
  echo "PowerContext 已在运行：$POWERCONTEXT_URL"
  exit 0
fi

if ! "$PYTHON" -c "import powercontext" > /dev/null 2>&1; then
  echo "缺少 powercontext，请先执行：pip install 'powercontext[cli,server]==1.4.1'" >&2
  exit 1
fi

setsid nohup "$PC_BIN" server run --env-file "$ENV_FILE" > "$SDDCTX_RUNTIME/powercontext.log" 2>&1 < /dev/null &
echo "$!" > "$SDDCTX_RUNTIME/powercontext.pid"

for _ in $(seq 1 30); do
  sleep 1
  if curl -sf -m 2 "$POWERCONTEXT_URL/health/ready" > /dev/null 2>&1; then
    echo "PowerContext 就绪：$POWERCONTEXT_URL"
    exit 0
  fi
done
echo "PowerContext 启动超时，日志：$SDDCTX_RUNTIME/powercontext.log" >&2
tail -20 "$SDDCTX_RUNTIME/powercontext.log" >&2 || true
exit 1
