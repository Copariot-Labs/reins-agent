#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
DEPLOY_STATE_DIR="$HOME/.config/reins"
REINS_HOME_STATE="$DEPLOY_STATE_DIR/reins-home"
REINS_HOME="${REINS_HOME:-}"
DISABLE_LINGER=0

log() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf 'Warning: %s\n' "$*" >&2
}

usage() {
  cat <<'EOF'
Usage: deploy/linux/uninstall.sh [options]

Remove Reins user services and desktop launchers. Application code and
~/.reins data are preserved.

Options:
  --disable-linger  Disable boot-time user services for this account.
  --reins-home PATH Reins data directory used during installation.
  -h, --help        Show this help.
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --disable-linger)
      DISABLE_LINGER=1
      ;;
    --reins-home)
      shift
      if (( $# == 0 )); then
        printf 'Error: --reins-home requires a path\n' >&2
        exit 1
      fi
      REINS_HOME="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Error: unknown option: %s\n' "$1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ -z "$REINS_HOME" && -r "$REINS_HOME_STATE" ]]; then
  IFS= read -r REINS_HOME < "$REINS_HOME_STATE"
fi
REINS_HOME="${REINS_HOME:-$HOME/.reins}"

case "$REINS_HOME" in
  "~")
    REINS_HOME="$HOME"
    ;;
  "~/"*)
    REINS_HOME="$HOME/${REINS_HOME:2}"
    ;;
esac
if [[ "$REINS_HOME" != /* ]]; then
  REINS_HOME="$PWD/$REINS_HOME"
fi
if command -v realpath >/dev/null 2>&1; then
  REINS_HOME="$(realpath -m -- "$REINS_HOME")"
fi

[[ "$(uname -s)" == "Linux" ]] || {
  printf 'Error: this uninstaller supports Linux only\n' >&2
  exit 1
}
(( EUID != 0 )) || {
  printf 'Error: run this uninstaller as the normal desktop user, not with sudo\n' >&2
  exit 1
}

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
REINS_BIN="$PROJECT_DIR/.venv/bin/reins"

log "Removing the WeCom ticket poller"
if [[ -x "$REINS_BIN" ]]; then
  if ! REINS_HOME="$REINS_HOME" HERMES_HOME="$REINS_HOME" \
    "$REINS_BIN" wecom ticket-api service uninstall; then
    warn "the Reins CLI could not uninstall the WeCom service; using file cleanup"
  fi
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now reins-wecom-ticket-poller.service >/dev/null 2>&1 || true
fi
rm -f -- "$SYSTEMD_USER_DIR/reins-wecom-ticket-poller.service"
rm -f -- "$REINS_HOME/wecom/ticket-poller.sh"

log "Removing the Web UI service"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now reins-web.service >/dev/null 2>&1 || true
  systemctl --user disable --now reins-gateway.service >/dev/null 2>&1 || true
fi
rm -f -- "$SYSTEMD_USER_DIR/reins-web.service"
rm -f -- "$SYSTEMD_USER_DIR/reins-gateway.service"
rm -f -- "$HOME/.local/bin/reins-web-runtime"

log "Removing desktop launchers"
rm -f -- "$HOME/.local/bin/reins-open"
rm -f -- "$HOME/.local/share/applications/reins.desktop"
rm -f -- "$HOME/.local/share/applications/Reins.desktop"

if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP)"
else
  DESKTOP_DIR="$HOME/Desktop"
fi
[[ -n "$DESKTOP_DIR" ]] || DESKTOP_DIR="$HOME/Desktop"
rm -f -- "$DESKTOP_DIR/Reins.desktop"
if [[ "$DESKTOP_DIR" != "$HOME/Desktop" ]]; then
  rm -f -- "$HOME/Desktop/Reins.desktop"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user reset-failed >/dev/null 2>&1 || true
fi

if (( DISABLE_LINGER )); then
  log "Disabling boot-time user services"
  sudo loginctl disable-linger "$(id -un)"
fi

log "Reins deployment removed"
printf 'Application code was preserved at: %s\n' "$PROJECT_DIR"
printf 'User data was preserved at:        %s\n' "$REINS_HOME"
rm -f -- "$REINS_HOME_STATE" "$DEPLOY_STATE_DIR/workspace"
rmdir "$DEPLOY_STATE_DIR" >/dev/null 2>&1 || true
