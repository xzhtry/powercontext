#!/usr/bin/env bash
# 把 Dify 已注册模型写到 evidence/dify-model.txt。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PASSWORD="${DIFY_DB_PASSWORD:-difypass}"
PGPASSWORD="$DB_PASSWORD" psql -h "${DIFY_DB_HOST:-127.0.0.1}" -U "${DIFY_DB_USER:-dify}" \
  -d "${DIFY_DB_NAME:-dify}" -f "$ROOT/scripts/dify_model.sql" > "$ROOT/evidence/dify-model.txt" 2>&1
echo "wrote $ROOT/evidence/dify-model.txt"
