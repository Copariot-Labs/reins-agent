#!/usr/bin/env bash
set -euo pipefail

REINS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REINS_ROOT"

if [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
fi

export REINS_HOME="${REINS_HOME:-$HOME/.reins}"
export HERMES_HOME="$REINS_HOME"
export HERMES_WEB_UI_HOME="${HERMES_WEB_UI_HOME:-$REINS_HOME/web-ui}"

export REINS_BIN="${REINS_BIN:-$(command -v reins)}"
export HERMES_BIN="${HERMES_BIN:-$REINS_BIN}"
export HERMES_AGENT_ROOT="${HERMES_AGENT_ROOT:-$REINS_ROOT/vendor/hermes-agent}"
export HERMES_AGENT_BRIDGE_PYTHON="${HERMES_AGENT_BRIDGE_PYTHON:-$REINS_ROOT/.venv/bin/python}"


cd "$REINS_ROOT/web"

npm run dev
