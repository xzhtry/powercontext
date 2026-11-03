#!/usr/bin/env bash
# 一键启动：PostgreSQL/Redis → Dify API → 客栈后端 → 网页入口。
# 适用于本机 Dify 源码部署；Docker 部署只需启动后端和网页入口。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

echo "== 1/4 数据库 =="
sudo service postgresql start >/dev/null 2>&1 || true
sudo service redis-server start >/dev/null 2>&1 || (redis-server --daemonize yes >/dev/null 2>&1 || true)
pg_isready -h 127.0.0.1 -p 5432 >/dev/null
redis-cli ping >/dev/null

echo "== 2/4 Dify API =="
if ! curl -sf -m 3 http://127.0.0.1:5001/console/api/setup >/dev/null 2>&1; then
  if [ -x "$HOME/.venvs/dify/bin/flask" ] && [ -d "$HOME/.local/share/dify/api" ]; then
    cd "$HOME/.local/share/dify/api"
    export FLASK_APP=app.py
    export FLASK_DEBUG=0
    setsid nohup "$HOME/.venvs/dify/bin/flask" run --host 0.0.0.0 --port 5001 \
      > /tmp/dify-api.log 2>&1 < /dev/null &
    echo "$!" > "$GRUDGE_INN_RUNTIME/dify-api.pid"
    for _ in $(seq 1 60); do
      if curl -sf -m 2 http://127.0.0.1:5001/console/api/setup >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  else
    echo "找不到 Dify 源码环境，跳过；网页入口仍可打开，但聊天会失败。" >&2
  fi
fi
curl -sf -m 3 http://127.0.0.1:5001/console/api/setup >/dev/null && echo "Dify API 就绪：http://127.0.0.1:5001"

echo "== 3/4 客栈后端 =="
bash "$GRUDGE_INN_ROOT/scripts/start.sh"

echo "== 4/4 网页入口 =="
bash "$GRUDGE_INN_ROOT/scripts/start_play.sh"
echo
echo "打开：http://127.0.0.1:8790"
