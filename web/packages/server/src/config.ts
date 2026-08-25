import { join, resolve } from 'path'
import { homedir } from 'os'
import { reinsWorkspaceDir, resolveReinsWorkspaceRoot } from './services/reins/workspace-path'

/**
 * Web UI environment variables.
 *
 * Server/listen:
 * - PORT: Web UI listen port. Default: 8648.
 * - BIND_HOST: Web UI bind host. Default: 0.0.0.0.
 * - CORS_ORIGINS: Koa CORS origin setting. Default: *.
 *
 * Web UI storage:
 * - HERMES_WEB_UI_HOME: Web UI data home for auth token, credentials, logs, DB, and default uploads.
 * - HERMES_WEBUI_STATE_DIR: Compatibility alias for HERMES_WEB_UI_HOME.
 *   Default: join(homedir(), '.hermes-web-ui').
 * - REINS_WORKSPACE_ROOT: Native user workspace. Default: ~/Documents/Reins Workspace.
 * - UPLOAD_DIR: Upload directory override. Default: REINS_WORKSPACE_ROOT/Inbox.
 *
 * Auth:
 * - AUTH_TOKEN: Explicit bearer token. If unset, Web UI stores an auto-generated token under HERMES_WEB_UI_HOME.
 *
 * Runtime behavior:
 * - PROFILE: Initial Hermes profile name. Default: default.
 * - GATEWAY_HOST: Default gateway host written into profile config. Default: 127.0.0.1.
 * - HERMES_WEB_UI_STOP_GATEWAYS_ON_SHUTDOWN: Whether Web UI shutdown also stops gateways.
 * - WORKSPACE_BASE: Base directory for workspace browsing. Default: /opt/data/workspace.
 *
 * Limits/logging:
 * - MAX_DOWNLOAD_SIZE: Max file download size. Default: 200MB.
 * - MAX_EDIT_SIZE: Max editable file size. Default: 10MB.
 * - LOG_LEVEL: Server log level. Default: info.
 * - BRIDGE_LOG_LEVEL: Bridge log level. Default: LOG_LEVEL or info.
 */

export function getListenHost(env: Record<string, string | undefined> = process.env): string {
  const host = env.BIND_HOST?.trim()
  return host || '0.0.0.0'
}

export function getWebUiHome(env: Record<string, string | undefined> = process.env): string {
  const appHome = env.HERMES_WEB_UI_HOME?.trim() || env.HERMES_WEBUI_STATE_DIR?.trim()
  return appHome ? resolve(appHome) : join(homedir(), '.hermes-web-ui')
}

export function getDataDir(
  env: Record<string, string | undefined> = process.env,
  webUiHome = getWebUiHome(env),
): string {
  return env.REINS_DESKTOP === '1'
    ? join(webUiHome, 'data')
    : resolve(__dirname, '..', 'data')
}

const appHome = getWebUiHome()
const workspaceRoot = resolveReinsWorkspaceRoot()

export const config = {
  port: parseInt(process.env.PORT || '8648', 10),
  // Default to IPv4 for stable WSL/Windows browser access. Use BIND_HOST=:: explicitly for IPv6.
  host: getListenHost(),
  appHome,
  workspaceRoot,
  uploadDir: process.env.UPLOAD_DIR || reinsWorkspaceDir('Inbox', workspaceRoot),
  // Installed resources may be read-only. Desktop databases belong in the
  // current user's private application-data directory.
  dataDir: getDataDir(process.env, appHome),
  corsOrigins: process.env.CORS_ORIGINS || '*',
}
