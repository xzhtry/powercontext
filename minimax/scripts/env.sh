#!/usr/bin/env bash
# 统一的环境变量：运行时目录、Python、PowerContext 地址。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${SDDCTX_RUNTIME:-}" ]; then
  case "$ROOT" in
    /mnt/*) SDDCTX_RUNTIME="$HOME/.local/share/sddctx" ;;
    *) SDDCTX_RUNTIME="$ROOT/runtime" ;;
  esac
fi
export SDDCTX_RUNTIME
export POWERCONTEXT_URL="${POWERCONTEXT_URL:-http://127.0.0.1:8765}"

if [ -n "${PYTHON:-}" ]; then
  :
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  PYTHON="python3"
fi
export PYTHON

PC_BIN="${PC_BIN:-$(dirname "$PYTHON")/powercontext}"
export PC_BIN
export SDDCTX="$PYTHON -m sddctx.cli"
