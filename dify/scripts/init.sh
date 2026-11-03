#!/usr/bin/env bash
# 首次初始化：启动 PowerContext + 客栈后端；seekdb 表结构与 46 张卡会自动建好。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

bash "$GRUDGE_INN_ROOT/scripts/start.sh"
echo "--- health ---"
curl -s "http://127.0.0.1:$GRUDGE_INN_PORT/health"
echo
echo "初始化完成。Dify 侧请导入 dsl/grudge-inn.chatflow.yml。"
