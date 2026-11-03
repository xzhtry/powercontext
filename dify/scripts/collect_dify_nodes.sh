#!/usr/bin/env bash
# 把 Dify 最近节点执行记录写到 evidence/dify-nodes.txt。
# 需要 Dify 使用 PostgreSQL，且本机有 psql；密码用 DIFY_DB_PASSWORD 覆盖。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_JSON="$HOME/.local/share/grudge-inn/dify-app.json"
APP_ID="${DIFY_APP_ID:-$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["app_id"])' "$APP_JSON")}"
DB_PASSWORD="${DIFY_DB_PASSWORD:-difypass}"
DB_HOST="${DIFY_DB_HOST:-127.0.0.1}"
DB_USER="${DIFY_DB_USER:-dify}"
DB_NAME="${DIFY_DB_NAME:-dify}"

PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
  -v app_id="$APP_ID" -f "$ROOT/scripts/dify_nodes.sql" \
  > "$ROOT/evidence/dify-nodes.txt" 2>&1
echo "wrote $ROOT/evidence/dify-nodes.txt"
