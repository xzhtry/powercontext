#!/usr/bin/env bash
# 验证“修改前失败、修改后通过”：
#   before = snapshots/before（目标测试已写好、实现缺失）
#   after  = demo_app（MiniMax 修改后的代码）
# 同一组测试文件在两份代码上运行，日志写入 evidence/tests/。
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
set +e
cd "$ROOT"
mkdir -p evidence/tests

TARGET="tests/test_min_amount_filter.py"
REGRESSION="tests/test_list_invoices.py tests/test_pagination.py tests/test_cli.py"

run_suite() {
  local app="$1" label="$2" spec="$3" log="$4"
  local version
  version="$(cd "$app" && find src -name '*.py' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16)"
  {
    echo "# app=$app"
    echo "# code_version=src-sha256:$version"
    echo "# command=$PYTHON -m pytest $spec"
    echo
  } > "$log"
  (cd "$app" && PYTHONPATH=src "$PYTHON" -m pytest $spec) >> "$log" 2>&1
  echo $? > "$log.exit"
}

rm -rf "$SDDCTX_RUNTIME/verify"
mkdir -p "$SDDCTX_RUNTIME/verify"
cp -a snapshots/before "$SDDCTX_RUNTIME/verify/before"

run_suite "$SDDCTX_RUNTIME/verify/before" before-target "$TARGET" evidence/tests/before-target.log
run_suite "$SDDCTX_RUNTIME/verify/before" before-regression "$REGRESSION" evidence/tests/before-regression.log
run_suite demo_app after-target "$TARGET" evidence/tests/after-target.log
run_suite demo_app after-regression "$REGRESSION" evidence/tests/after-regression.log
run_suite demo_app after-full "" evidence/tests/after-full.log

before_target="$(cat evidence/tests/before-target.log.exit)"
before_regression="$(cat evidence/tests/before-regression.log.exit)"
after_target="$(cat evidence/tests/after-target.log.exit)"
after_regression="$(cat evidence/tests/after-regression.log.exit)"
after_full="$(cat evidence/tests/after-full.log.exit)"

echo "before target      exit=$before_target (期望非 0)"
echo "before regression  exit=$before_regression (期望 0)"
echo "after  target       exit=$after_target (期望 0)"
echo "after  regression   exit=$after_regression (期望 0)"
echo "after  full         exit=$after_full (期望 0)"

if [ "$before_target" -ne 0 ] && [ "$before_regression" -eq 0 ] \
   && [ "$after_target" -eq 0 ] && [ "$after_regression" -eq 0 ] && [ "$after_full" -eq 0 ]; then
  echo "PASS：目标测试修改前失败、修改后通过；回归测试始终通过。"
  exit 0
fi
echo "FAIL：修改前后测试结果不符合预期" >&2
exit 1
