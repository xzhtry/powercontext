#!/usr/bin/env bash
# 统一环境变量。默认把运行态放在 Linux 文件系统（WSL 的 /mnt/* 不能跑嵌入式 seekdb）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export GRUDGE_INN_ROOT="$ROOT"
export GRUDGE_INN_RUNTIME="${GRUDGE_INN_RUNTIME:-$HOME/.local/share/grudge-inn}"
export GRUDGE_INN_SEEKDB="${GRUDGE_INN_SEEKDB:-$GRUDGE_INN_RUNTIME/seekdb}"
export GRUDGE_INN_PORT="${GRUDGE_INN_PORT:-8787}"
export GRUDGE_INN_PLAY_PORT="${GRUDGE_INN_PLAY_PORT:-8790}"
export GRUDGE_INN_POWERCONTEXT_URL="${GRUDGE_INN_POWERCONTEXT_URL:-http://127.0.0.1:8766}"
export GRUDGE_INN_POWERCONTEXT_PORT="${GRUDGE_INN_POWERCONTEXT_PORT:-8766}"

if [ -n "${GRUDGE_INN_PYTHON:-}" ]; then
  PYTHON="$GRUDGE_INN_PYTHON"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
elif [ -x "$HOME/.venvs/dify-inn/bin/python" ]; then
  PYTHON="$HOME/.venvs/dify-inn/bin/python"
else
  PYTHON="python3"
fi
export PYTHON
export PC_BIN="${PC_BIN:-$(dirname "$PYTHON")/powercontext}"

mkdir -p "$GRUDGE_INN_RUNTIME" "$GRUDGE_INN_SEEKDB"
