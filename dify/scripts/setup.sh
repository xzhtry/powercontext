#!/usr/bin/env bash
# 创建后端 Python 环境。Dify 本身请按 docs/dify-setup.md 单独部署。
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"

if ! command -v python3 >/dev/null 2>&1; then
  echo "需要 Python 3.11+（实测 3.12）" >&2
  exit 1
fi
python3 - <<'PY'
import sys
assert sys.version_info >= (3, 11), "Python 3.11+ required"
PY

if [ ! -x "$GRUDGE_INN_ROOT/.venv/bin/python" ]; then
  python3 -m venv "$GRUDGE_INN_ROOT/.venv"
fi
source "$GRUDGE_INN_ROOT/.venv/bin/activate"
python -m pip install -q --upgrade pip
python -m pip install -q -r "$GRUDGE_INN_ROOT/requirements.txt"
python -c "import pylibseekdb, powercontext; print('backend deps OK')"
echo "后端环境就绪：$GRUDGE_INN_ROOT/.venv"
echo "下一步：bash scripts/init.sh"
