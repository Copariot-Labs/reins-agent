#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'
umask 077

STATE_DIR="${REINS_DEPLOY_STATE_DIR:-$HOME/.config/reins}"
PROJECT_STATE="$STATE_DIR/project-root"
REINS_HOME_STATE="$STATE_DIR/reins-home"
WORKSPACE_STATE="$STATE_DIR/workspace"
INSTALL_WECOM_STATE="$STATE_DIR/install-wecom"
INSTALL_DESKTOP_STATE="$STATE_DIR/install-desktop"
ENABLE_LINGER_STATE="$STATE_DIR/enable-linger"

read_state() {
  local path="$1"
  local fallback="$2"
  local value=""
  if [[ -r "$path" ]]; then
    IFS= read -r value < "$path"
  fi
  printf '%s' "${value:-$fallback}"
}

PROJECT_DIR="$(read_state "$PROJECT_STATE" "")"
REINS_HOME="$(read_state "$REINS_HOME_STATE" "$HOME/.reins")"
WORKSPACE_DIR="$(read_state "$WORKSPACE_STATE" "$HOME/Documents/Reins")"
INSTALL_WECOM="$(read_state "$INSTALL_WECOM_STATE" "1")"
INSTALL_DESKTOP="$(read_state "$INSTALL_DESKTOP_STATE" "1")"
ENABLE_LINGER="$(read_state "$ENABLE_LINGER_STATE" "1")"
LOG_DIR="$REINS_HOME/logs"
LOG_FILE="$LOG_DIR/update.log"
STATUS_FILE="$LOG_DIR/update-status.json"

mkdir -p -- "$LOG_DIR"
chmod 700 "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

write_status() {
  local status="$1"
  local message="$2"
  local temporary="$STATUS_FILE.tmp.$$"
  printf '{"status":"%s","message":"%s","updated_at":"%s"}\n' \
    "$status" "$message" "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" > "$temporary"
  chmod 600 "$temporary"
  mv -f -- "$temporary" "$STATUS_FILE"
}

notify_user() {
  local message="$1"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "Reins Update" "$message" >/dev/null 2>&1 || true
  fi
}

[[ -n "$PROJECT_DIR" ]] || {
  write_status "failed" "The installed project path is missing."
  exit 1
}
[[ -d "$PROJECT_DIR/.git" ]] || {
  write_status "failed" "The installed Reins directory is not a Git checkout."
  exit 1
}
[[ -x "$PROJECT_DIR/deploy/linux/install.sh" ]] || {
  write_status "failed" "The Linux installer is missing from the Reins checkout."
  exit 1
}

command -v flock >/dev/null 2>&1 || {
  write_status "failed" "The flock command is required to update Reins."
  exit 1
}
command -v git >/dev/null 2>&1 || {
  write_status "failed" "Git is required to update Reins."
  exit 1
}

exec 9> "$STATE_DIR/update.lock"
if ! flock -n 9; then
  write_status "failed" "Another Reins update is already running."
  exit 1
fi

web_was_active=0
wecom_was_active=0
if systemctl --user is-active --quiet reins-web.service; then
  web_was_active=1
fi
if systemctl --user is-active --quiet reins-wecom-ticket-poller.service; then
  wecom_was_active=1
fi

restore_services() {
  local exit_code=$?
  if (( exit_code == 0 )); then
    return
  fi

  write_status "failed" "The update failed. See the Reins update log for details."
  if (( web_was_active )); then
    systemctl --user start reins-web.service >/dev/null 2>&1 || true
  fi
  if (( wecom_was_active )); then
    systemctl --user start reins-wecom-ticket-poller.service >/dev/null 2>&1 || true
  fi
  notify_user "Update failed. Ask support to check $LOG_FILE"
  exit "$exit_code"
}
trap restore_services EXIT

write_status "running" "Downloading and installing the latest Reins version."
printf '\n[%s] Starting Reins update\n' "$(date -Is)"

# Give the Web request enough time to return before its service is stopped.
sleep "${REINS_UPDATE_DELAY_SECONDS:-3}"
systemctl --user stop reins-web.service
if (( wecom_was_active )); then
  systemctl --user stop reins-wecom-ticket-poller.service
fi

git -C "$PROJECT_DIR" pull --ff-only

install_args=(
  --reins-home "$REINS_HOME"
  --workspace "$WORKSPACE_DIR"
)
if [[ "$INSTALL_WECOM" != "1" ]]; then
  install_args+=(--skip-wecom)
fi
if [[ "$INSTALL_DESKTOP" != "1" ]]; then
  install_args+=(--no-desktop)
fi
if [[ "$ENABLE_LINGER" != "1" ]]; then
  install_args+=(--no-linger)
fi

"$PROJECT_DIR/deploy/linux/install.sh" "${install_args[@]}"

if [[ "$INSTALL_WECOM" != "1" ]] && (( wecom_was_active )); then
  systemctl --user start reins-wecom-ticket-poller.service
fi

trap - EXIT
write_status "success" "Reins was updated successfully."
notify_user "Reins was updated successfully."
printf '[%s] Reins update completed\n' "$(date -Is)"
