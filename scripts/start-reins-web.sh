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

exec reins web "$@"
