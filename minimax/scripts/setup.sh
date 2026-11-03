#!/usr/bin/env bash
# 创建虚拟环境并安装依赖（Linux / WSL2）。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install "powercontext[cli,server]==1.4.1"
echo "依赖安装完成。复制 .env.example 为 .env 并填写 MINIMAX_API_KEY，然后执行 bash scripts/init.sh"
