#!/usr/bin/env bash
# 演示任务状态跨进程复用：
#   1) 若当前没有任务状态，先用参考补丁跑一次，写入 PowerContext；
#   2) 重启 PowerContext Server 与 sddctx 进程；
#   3) 新进程读取状态，并把状态用于新构造的上下文。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$ROOT"
mkdir -p evidence/state

echo "== 1. 读取/创建任务状态 =="
"$PYTHON" -m sddctx.cli state --json evidence/state/before-restart.json > /dev/null 2>&1 || true
if ! "$PYTHON" -c 'import json,sys; s=json.load(open("evidence/state/before-restart.json")); sys.exit(0 if s.get("run_seq") else 1)' 2>/dev/null; then
  echo "   当前为空状态，先用参考补丁执行一次任务"
  "$PYTHON" -m sddctx.cli run --patch changes/final-minimax.diff > /dev/null
  "$PYTHON" -m sddctx.cli state --json evidence/state/before-restart.json > /dev/null
fi

BEFORE_RUN="$("$PYTHON" -c 'import json; s=json.load(open("evidence/state/before-restart.json")); print(s["run_seq"])')"
BEFORE_STATUS="$("$PYTHON" -c 'import json; s=json.load(open("evidence/state/before-restart.json")); print(s["status"])')"
echo "   重启前：run_seq=$BEFORE_RUN status=$BEFORE_STATUS"

echo "== 2. 重启 PowerContext 与上下文模块进程 =="
if [ -f "$SDDCTX_RUNTIME/powercontext.pid" ]; then
  kill "$(cat "$SDDCTX_RUNTIME/powercontext.pid")" 2>/dev/null || true
fi
pkill -f "powercontext server run --env-file $SDDCTX_RUNTIME/powercontext.env" 2>/dev/null || true
sleep 2
bash "$ROOT/scripts/start_powercontext.sh" > /dev/null
echo "   PowerContext 已重启"

echo "== 3. 新进程读取并使用状态 =="
"$PYTHON" -m sddctx.cli state --json evidence/state/after-restart.json > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/state/context-after-restart.json > /dev/null

"$PYTHON" - <<'PY'
import json
before = json.load(open("evidence/state/before-restart.json", encoding="utf-8"))
after = json.load(open("evidence/state/after-restart.json", encoding="utf-8"))
context = json.load(open("evidence/state/context-after-restart.json", encoding="utf-8"))
assert after["run_seq"] == before["run_seq"], (before["run_seq"], after["run_seq"])
assert after["status"] == before["status"]
assert after["completed"], "重启后没有读到已完成事项"
assert context["state"]["run_seq"] == before["run_seq"]
assert context["state"]["completed"] == before["completed"]
print(f"   OK：重启后读到 run_seq={after['run_seq']} status={after['status']}，"
      f"并进入上下文（{len(context['state']['completed'])} 项已完成）")
PY

echo "PASS：任务状态在模块/服务重启后仍可读取并用于后续上下文。"
