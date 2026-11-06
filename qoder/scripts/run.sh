#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "尚未安装依赖。先运行：bash scripts/setup.sh" >&2
  exit 1
fi

export RT_RUNTIME="${RT_RUNTIME:-$HOME/ResearchThread}"
export RT_PORT="${RT_PORT:-8787}"
export RT_SEEKDB_PORT="${RT_SEEKDB_PORT:-18881}"
export RT_PC_PORT="${RT_PC_PORT:-18765}"

echo "研脉 ResearchThread"
echo "  runtime:       $RT_RUNTIME"
echo "  web:           http://127.0.0.1:$RT_PORT"
echo "  seekdb port:   $RT_SEEKDB_PORT (Linux 使用嵌入式模式时忽略)"
echo "  PowerContext:  http://127.0.0.1:$RT_PC_PORT"
echo
. .venv/bin/activate
exec python -m app
