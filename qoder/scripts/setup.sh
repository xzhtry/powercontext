#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3.11+" >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv
fi
. .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt
echo
echo "安装完成。运行：bash scripts/run.sh"
