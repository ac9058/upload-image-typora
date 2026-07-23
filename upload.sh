#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer project venv so Typora (minimal PATH) does not hit /usr/bin/python3
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PY="$SCRIPT_DIR/.venv/bin/python"
elif [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
  PY="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "未找到 Python 3，请先安装并加入 PATH。" >&2
  echo "或在项目目录执行: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

exec "$PY" "$SCRIPT_DIR/upload.py" "$@"
