#!/usr/bin/env bash
# 初始化：启动 PowerContext，导入 demo 工程的规格/代码/测试到 seekdb。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

bash "$ROOT/scripts/start_powercontext.sh"
cd "$ROOT"
$SDDCTX init
$SDDCTX context --json "$ROOT/evidence/context/initial.json" --no-state > /dev/null
echo "初始化完成。数据库：$SDDCTX_RUNTIME/seekdb"
