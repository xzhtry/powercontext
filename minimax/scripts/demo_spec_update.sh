#!/usr/bin/env bash
# 演示规格演进：同一任务在规格更新并重新导入后，上下文使用 v2 内容；
# 恢复 v1 后重新导入，上下文再次使用 v1，证明不是固定答案。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
cd "$ROOT"
mkdir -p evidence/spec-update
LOG=evidence/spec-update/run.log
exec > >(tee "$LOG") 2>&1

SPEC=demo_app/specs/REQ-INV-004-invoice-list-filtering.md
V1=samples/spec-update/REQ-INV-004.v1.md
V2=samples/spec-update/REQ-INV-004.v2.md

check() {
  local file="$1" want_version="$2" want_text="$3"
  "$PYTHON" - "$file" "$want_version" "$want_text" <<'PY'
import json, sys
path, want_version, want_text = sys.argv[1], int(sys.argv[2]), sys.argv[3]
ctx = json.load(open(path, encoding="utf-8"))
items = [s for s in ctx["specs"] if s["section_id"] == "REQ-INV-004.2"]
if not items:
    raise SystemExit(f"上下文中缺少 REQ-INV-004.2：{[s['section_id'] for s in ctx['specs']]}")
item = items[0]
assert item["version"] == want_version, (item["version"], want_version)
assert want_text in item["text"], f"上下文中未找到 {want_text!r}"
print(f"  OK: REQ-INV-004.2 v{item['version']} 包含 {want_text!r}")
PY
}

echo "== 1. 导入 v1，构造上下文 =="
cp "$V1" "$SPEC"
"$PYTHON" -m sddctx.cli import > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/spec-update/context-v1.json > /dev/null
check evidence/spec-update/context-v1.json 1 "小于 0"

echo "== 2. 更新为 v2 并重新导入，构造上下文 =="
cp "$V2" "$SPEC"
"$PYTHON" -m sddctx.cli import > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/spec-update/context-v2.json > /dev/null
check evidence/spec-update/context-v2.json 2 "零值"

echo "== 3. 恢复 v1 并重新导入，确认上下文回到 v1 =="
cp "$V1" "$SPEC"
"$PYTHON" -m sddctx.cli import > /dev/null
"$PYTHON" -m sddctx.cli context --json evidence/spec-update/context-restored.json > /dev/null
check evidence/spec-update/context-restored.json 1 "小于 0"

echo "PASS：规格更新并重新导入后，上下文使用更新后的内容；恢复后同样生效。"
