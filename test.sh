#!/usr/bin/env bash
# Local checks: lint + offline tests. Never touches hardware and never sets
# LITEARM_LIVE, so the live tests stay skipped.
set -euo pipefail

cd "$(dirname "$0")"

if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
else
    PYTHON=python3
fi

if [ -x .venv/bin/ruff ]; then
    RUFF=.venv/bin/ruff
elif command -v ruff >/dev/null 2>&1; then
    RUFF=ruff
else
    RUFF=
fi

if [ -n "$RUFF" ]; then
    "$RUFF" check src tests examples
else
    echo "warning: ruff not installed; skipping lint" >&2
fi

exec "$PYTHON" -m pytest "$@"
