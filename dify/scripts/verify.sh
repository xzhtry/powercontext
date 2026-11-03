#!/usr/bin/env bash
# 后端单元测试 + 运行态验收。要求 scripts/init.sh 已启动服务。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$GRUDGE_INN_ROOT"

echo "--- pytest ---"
"$PYTHON" -m pytest -q tests
echo "--- live verification ---"
"$PYTHON" scripts/verify_live.py
