#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
TARGET_USER="$(id -un)"
DEPLOY_STATE_DIR="$HOME/.config/reins"
REINS_HOME_STATE="$DEPLOY_STATE_DIR/reins-home"
WORKSPACE_STATE="$DEPLOY_STATE_DIR/workspace"
PROJECT_STATE="$DEPLOY_STATE_DIR/project-root"
INSTALL_WECOM_STATE="$DEPLOY_STATE_DIR/install-wecom"
INSTALL_DESKTOP_STATE="$DEPLOY_STATE_DIR/install-desktop"
ENABLE_LINGER_STATE="$DEPLOY_STATE_DIR/enable-linger"

BUILD_APP=1
INSTALL_WECOM=1
ENABLE_LINGER=1
INSTALL_DESKTOP=1
REINS_HOME_INPUT="${REINS_HOME:-}"
WORKSPACE_INPUT="${REINS_WORKSPACE_BASE:-}"

if [[ -z "$REINS_HOME_INPUT" && -r "$REINS_HOME_STATE" ]]; then
  IFS= read -r REINS_HOME_INPUT < "$REINS_HOME_STATE"
fi
if [[ -z "$WORKSPACE_INPUT" && -r "$WORKSPACE_STATE" ]]; then
  IFS= read -r WORKSPACE_INPUT < "$WORKSPACE_STATE"
fi
REINS_HOME_INPUT="${REINS_HOME_INPUT:-$HOME/.reins}"
WORKSPACE_INPUT="${WORKSPACE_INPUT:-$HOME/Documents/Reins}"

log() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf 'Warning: %s\n' "$*" >&2
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: deploy/linux/install.sh [options]

Install Reins for the current Ubuntu desktop user.

Options:
  --skip-build          Use the existing Python environment and Web UI build.
  --skip-wecom          Do not install the WeCom ticket poller.
  --no-linger           Start services at login instead of system boot.
  --no-desktop          Do not install the application-menu/desktop launcher.
  --reins-home PATH     Reins data directory (default: ~/.reins).
  --workspace PATH      User workspace directory (default: ~/Documents/Reins).
  -h, --help            Show this help.

Run this script as the normal desktop user, never with sudo.
EOF
}

normalize_path() {
  local value="$1"
  case "$value" in
    "~")
      value="$HOME"
      ;;
    "~/"*)
      value="$HOME/${value:2}"
      ;;
  esac
  if [[ "$value" != /* ]]; then
    value="$PWD/$value"
  fi
  realpath -m -- "$value"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

systemd_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//\$/\$\$}"
  value="${value//\%/%%}"
  printf '"%s"' "$value"
}

shell_quote() {
  printf '%q' "$1"
}

desktop_exec_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//\$/\\\$}"
  value="${value//\`/\\\`}"
  printf '"%s"' "$value"
}

write_atomic() {
  local destination="$1"
  local mode="$2"
  local temporary
  temporary="$(mktemp "${destination}.tmp.XXXXXX")"
  cat > "$temporary"
  chmod "$mode" "$temporary"
  mv -f -- "$temporary" "$destination"
}

wait_for_web() {
  local attempts=240
  while (( attempts > 0 )); do
    if curl -fsS "http://127.0.0.1:8648/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
    attempts=$((attempts - 1))
  done
  return 1
}

while (( $# > 0 )); do
  case "$1" in
    --skip-build)
      BUILD_APP=0
      ;;
    --skip-wecom)
      INSTALL_WECOM=0
      ;;
    --no-linger)
      ENABLE_LINGER=0
      ;;
    --no-desktop)
      INSTALL_DESKTOP=0
      ;;
    --reins-home)
      shift
      (( $# > 0 )) || die "--reins-home requires a path"
      REINS_HOME_INPUT="$1"
      ;;
    --workspace)
      shift
      (( $# > 0 )) || die "--workspace requires a path"
      WORKSPACE_INPUT="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
  shift
done

[[ "$(uname -s)" == "Linux" ]] || die "this installer supports Linux only"
(( EUID != 0 )) || die "do not run this installer with sudo; run it as the desktop user"

require_command realpath
require_command systemctl
require_command loginctl
require_command node
require_command curl
require_command git
require_command flock
if (( INSTALL_DESKTOP )); then
  require_command xdg-open
fi

REINS_HOME="$(normalize_path "$REINS_HOME_INPUT")"
WORKSPACE_DIR="$(normalize_path "$WORKSPACE_INPUT")"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
REINS_BIN="$PROJECT_DIR/.venv/bin/reins"
WEB_ROOT="$PROJECT_DIR/web"
WEB_SERVER="$WEB_ROOT/dist/server/index.js"
WEB_CLIENT="$WEB_ROOT/dist/client/index.html"
WEB_ICON="$WEB_ROOT/dist/client/logo.jpg"
UPDATE_SOURCE="$PROJECT_DIR/deploy/linux/update.sh"
NODE_BIN="$(command -v node)"
NODE_BIN="$(readlink -f -- "$NODE_BIN")"
NODE_MAJOR="$("$NODE_BIN" -p "Number(process.versions.node.split('.')[0])")"

[[ "$NODE_MAJOR" =~ ^[0-9]+$ ]] || die "could not determine the Node.js version"
(( NODE_MAJOR >= 23 )) || die "Node.js 23 or newer is required; found $("$NODE_BIN" --version)"

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "ubuntu" && "${ID_LIKE:-}" != *ubuntu* && "${ID_LIKE:-}" != *debian* ]]; then
    warn "this installer is tested for Ubuntu; detected ${PRETTY_NAME:-unknown Linux}"
  fi
fi

log "Preparing directories"
install -d -m 700 "$REINS_HOME"
install -d -m 700 "$REINS_HOME/logs"
install -d -m 700 "$REINS_HOME/web-ui"
install -d -m 700 "$WORKSPACE_DIR"
install -d -m 700 "$DEPLOY_STATE_DIR"
install -d -m 700 "$HOME/.config/systemd/user"
install -d -m 700 "$HOME/.local/bin"
install -d -m 700 "$HOME/.local/share/applications"

write_atomic "$REINS_HOME_STATE" 600 <<EOF
$REINS_HOME
EOF
write_atomic "$WORKSPACE_STATE" 600 <<EOF
$WORKSPACE_DIR
EOF
write_atomic "$PROJECT_STATE" 600 <<EOF
$PROJECT_DIR
EOF
write_atomic "$INSTALL_WECOM_STATE" 600 <<EOF
$INSTALL_WECOM
EOF
write_atomic "$INSTALL_DESKTOP_STATE" 600 <<EOF
$INSTALL_DESKTOP
EOF
write_atomic "$ENABLE_LINGER_STATE" 600 <<EOF
$ENABLE_LINGER
EOF

if [[ -f "$REINS_HOME/.env" ]]; then
  chmod 600 "$REINS_HOME/.env"
elif (( INSTALL_WECOM )); then
  die "missing $REINS_HOME/.env; configure it first or run with --skip-wecom"
else
  warn "$REINS_HOME/.env does not exist; model/provider setup must be completed in Reins"
fi

if (( BUILD_APP )); then
  require_command uv
  require_command npm

  [[ -f "$PROJECT_DIR/vendor/hermes-agent/run_agent.py" ]] \
    || die "Vendored Hermes source is incomplete: $PROJECT_DIR/vendor/hermes-agent"

  if [[ ! -x "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -c \
    "import sys; raise SystemExit(0 if sys.platform.startswith('linux') and sys.version_info >= (3, 11) else 1)" \
    >/dev/null 2>&1; then
    log "Creating a Linux Python virtual environment"
    uv venv --clear "$PROJECT_DIR/.venv"
  fi

  log "Installing Python packages"
  uv pip install --python "$PYTHON_BIN" -e "$PROJECT_DIR/vendor/hermes-agent"
  uv pip install --python "$PYTHON_BIN" -e "$PROJECT_DIR"

  log "Building the production Web UI"
  (
    cd "$WEB_ROOT"
    npm ci
    npm run build
  )
fi

[[ -x "$PYTHON_BIN" ]] || die "Python environment not found: $PYTHON_BIN"
[[ -x "$REINS_BIN" ]] || die "Reins executable not found: $REINS_BIN"
[[ -f "$WEB_SERVER" ]] || die "production Web server not found: $WEB_SERVER"
[[ -f "$WEB_CLIENT" ]] || die "production Web client not found: $WEB_CLIENT"
if (( INSTALL_DESKTOP )); then
  [[ -f "$WEB_ICON" ]] || die "Reins desktop icon not found: $WEB_ICON"
fi

if ! REINS_HOME="$REINS_HOME" HERMES_HOME="$REINS_HOME" \
  "$PYTHON_BIN" -c "import reins.main"; then
  die "the project Python environment cannot import reins.main"
fi

if (( INSTALL_WECOM )); then
  log "Validating WeCom ticket API configuration"
  REINS_HOME="$REINS_HOME" HERMES_HOME="$REINS_HOME" \
    "$REINS_BIN" wecom ticket-api doctor --json

  log "Installing and enabling the Reins WeCom plugin"
  REINS_HOME="$REINS_HOME" HERMES_HOME="$REINS_HOME" \
    "$REINS_BIN" wecom install-plugin
  REINS_HOME="$REINS_HOME" HERMES_HOME="$REINS_HOME" \
    "$REINS_BIN" plugins enable reins-wecom --no-allow-tool-override
fi

if (( ENABLE_LINGER )); then
  LINGER_STATE="$(loginctl show-user "$TARGET_USER" -p Linger --value 2>/dev/null || true)"
  if [[ "$LINGER_STATE" != "yes" ]]; then
    require_command sudo
    log "Enabling services at system boot"
    sudo loginctl enable-linger "$TARGET_USER"
  fi
else
  warn "user lingering is disabled; Reins services will start after desktop login"
fi

if ! systemctl --user show-environment >/dev/null 2>&1; then
  die "the systemd user manager is unavailable; log into the Ubuntu desktop as $TARGET_USER and rerun"
fi

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
WEB_UNIT="$SYSTEMD_USER_DIR/reins-web.service"
WEB_RUNTIME="$HOME/.local/bin/reins-web-runtime"
UPDATE_UNIT="$SYSTEMD_USER_DIR/reins-update.service"
UPDATE_RUNTIME="$HOME/.local/bin/reins-update"
RUNTIME_PATH="$PROJECT_DIR/.venv/bin:$(dirname -- "$NODE_BIN"):/usr/local/bin:/usr/bin:/bin"

[[ -f "$UPDATE_SOURCE" ]] || die "Linux updater not found: $UPDATE_SOURCE"
write_atomic "$UPDATE_RUNTIME" 700 < "$UPDATE_SOURCE"

log "Generating the Reins update service"
write_atomic "$UPDATE_UNIT" 600 <<EOF
[Unit]
Description=Update Reins Agent
After=network-online.target

[Service]
Type=oneshot
ExecStart=$(systemd_quote "$UPDATE_RUNTIME")
TimeoutStartSec=infinity
EOF

log "Generating the production Web UI runtime"
write_atomic "$WEB_RUNTIME" 700 <<EOF
#!/bin/bash

set -Eeuo pipefail
umask 077

export NODE_ENV=production
export PORT=8648
export BIND_HOST=127.0.0.1
export REINS_HOME=$(shell_quote "$REINS_HOME")
export HERMES_HOME=$(shell_quote "$REINS_HOME")
export HERMES_WEB_UI_HOME=$(shell_quote "$REINS_HOME/web-ui")
export HERMES_AGENT_ROOT=$(shell_quote "$PROJECT_DIR/vendor/hermes-agent")
export HERMES_AGENT_BRIDGE_PYTHON=$(shell_quote "$PYTHON_BIN")
export REINS_BIN=$(shell_quote "$REINS_BIN")
export HERMES_BIN=$(shell_quote "$REINS_BIN")
export WORKSPACE_BASE=$(shell_quote "$WORKSPACE_DIR")
export PATH=$(shell_quote "$RUNTIME_PATH")
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
export SHELL=/bin/bash
export HERMES_WEB_UI_DISABLE_UPDATE_CHECK=true
export REINS_UPDATE_SERVICE=reins-update.service

cd -- $(shell_quote "$WEB_ROOT")
exec $(shell_quote "$NODE_BIN") $(shell_quote "$WEB_SERVER")
EOF

log "Generating the production Web UI service"
write_atomic "$WEB_UNIT" 600 <<EOF
[Unit]
Description=Reins Web Interface

[Service]
Type=simple
ExecStart=$(systemd_quote "$WEB_RUNTIME")
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=default.target
EOF

LEGACY_GATEWAY_UNIT="$SYSTEMD_USER_DIR/reins-gateway.service"
if [[ -f "$LEGACY_GATEWAY_UNIT" ]]; then
  log "Removing the obsolete standalone gateway service"
  if ! systemctl --user disable --now reins-gateway.service; then
    warn "the old gateway service was not running or could not be stopped"
  fi
  rm -f -- "$LEGACY_GATEWAY_UNIT"
fi

log "Starting the production Web UI"
systemctl --user daemon-reload
if command -v systemd-analyze >/dev/null 2>&1; then
  if ! systemd-analyze --user verify "$WEB_UNIT" "$UPDATE_UNIT"; then
    die "systemd rejected a generated Reins unit"
  fi
fi
systemctl --user enable reins-web.service
if ! systemctl --user restart reins-web.service; then
  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze --user verify "$WEB_UNIT" || true
  fi
  systemctl --user status reins-web.service --no-pager || true
  die "could not restart reins-web.service"
fi

if ! wait_for_web; then
  systemctl --user status reins-web.service --no-pager || true
  journalctl --user -u reins-web.service -n 100 --no-pager || true
  die "Reins Web UI did not become healthy at http://127.0.0.1:8648"
fi

if (( INSTALL_WECOM )); then
  log "Installing the supported WeCom ticket poller"
  REINS_HOME="$REINS_HOME" \
  HERMES_HOME="$REINS_HOME" \
  REINS_SERVICE_PYTHON="$PYTHON_BIN" \
    "$REINS_BIN" wecom ticket-api service install

  REINS_HOME="$REINS_HOME" HERMES_HOME="$REINS_HOME" \
    "$REINS_BIN" wecom ticket-api service status
fi

if (( INSTALL_DESKTOP )); then
  OPEN_REINS="$HOME/.local/bin/reins-open"
  APPLICATION_FILE="$HOME/.local/share/applications/reins.desktop"

  log "Installing the desktop launcher"
  write_atomic "$OPEN_REINS" 700 <<'EOF'
#!/bin/sh

URL="http://127.0.0.1:8648"
attempts=120

systemctl --user start reins-web.service >/dev/null 2>&1 || exit 1

while [ "$attempts" -gt 0 ]; do
  if curl -fsS "$URL/health" >/dev/null 2>&1; then
    exec xdg-open "$URL"
  fi
  sleep 0.5
  attempts=$((attempts - 1))
done

if command -v notify-send >/dev/null 2>&1; then
  notify-send "Reins" "The Web interface could not be started."
fi
exit 1
EOF

  write_atomic "$APPLICATION_FILE" 700 <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Reins
Comment=Open Reins
Exec=$(desktop_exec_quote "$OPEN_REINS")
Icon=$WEB_ICON
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

  rm -f -- "$HOME/.local/share/applications/Reins.desktop"

  if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$APPLICATION_FILE"
  fi
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications"
  fi

  if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP)"
  else
    DESKTOP_DIR="$HOME/Desktop"
  fi
  [[ -n "$DESKTOP_DIR" ]] || DESKTOP_DIR="$HOME/Desktop"
  mkdir -p "$DESKTOP_DIR"
  install -m 700 "$APPLICATION_FILE" "$DESKTOP_DIR/Reins.desktop"

  if command -v gio >/dev/null 2>&1; then
    if ! gio set "$DESKTOP_DIR/Reins.desktop" metadata::trusted true; then
      warn "Ubuntu may require right-clicking Reins.desktop and selecting Allow Launching"
    fi
  fi
fi

log "Reins installation completed"
printf 'Application:    %s\n' "$PROJECT_DIR"
printf 'Data:           %s\n' "$REINS_HOME"
printf 'Web interface:  http://127.0.0.1:8648\n'
printf 'Web service:    systemctl --user status reins-web.service\n'
printf 'Update service: systemctl --user status reins-update.service\n'
if (( INSTALL_WECOM )); then
  printf 'WeCom service:  %s wecom ticket-api service status\n' "$REINS_BIN"
else
  printf 'WeCom service:  skipped\n'
fi
printf 'Web logs:       journalctl --user -u reins-web.service -f\n'
printf '\nInitial Web login: admin / 123456. Change this password immediately.\n'
