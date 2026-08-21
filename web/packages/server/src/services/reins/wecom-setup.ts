import { execFile } from 'child_process';
import { chmod, mkdir, readFile, rename, writeFile } from 'fs/promises';
import { dirname, join } from 'path';
import { promisify } from 'util';
import { resolveReinsHome } from './reins-path';

const execFileAsync = promisify(execFile);

const EDITABLE_KEYS = [
  'REINS_TICKET_API_URL',
  'REINS_TICKET_API_TOKEN',
  'REINS_TICKET_API_STATUSES',
  'REINS_TICKET_API_LIMIT',
  'REINS_TICKET_API_POLL_INTERVAL',
  'REINS_TICKET_API_TIMEOUT',

  'REINS_WECOM_NOTIFY_ENABLED',
  'REINS_WECOM_NOTIFY_GROUP_WEBHOOK',
  'REINS_WECOM_REPLY_BOT_NAME',

  'REINS_WECOM_NOTIFY_USERS_PROPERTY',
  'REINS_WECOM_NOTIFY_USERS_CLEANING',
  'REINS_WECOM_NOTIFY_USERS_POLICE',
  'REINS_WECOM_NOTIFY_USERS_HOSPITAL',
  'REINS_WECOM_NOTIFY_USERS_COMMUNITY',
  'REINS_WECOM_NOTIFY_USERS_HUMAN_REVIEW',
  'REINS_WECOM_NOTIFY_USERS_DEFAULT',

  'REINS_WECOM_EXPORT_DIR',
  'REINS_WECOM_ROUTING_MODE',
  'REINS_WECOM_ROUTING_CONFIDENCE',
  'REINS_WECOM_ROUTING_TIMEOUT',
] as const;

type EditableKey = (typeof EDITABLE_KEYS)[number];

const SECRET_KEYS = new Set<EditableKey>([
  'REINS_TICKET_API_TOKEN',
  'REINS_WECOM_NOTIFY_GROUP_WEBHOOK',
]);

export interface WeComSetupInput {
  ticket_api_url?: string;
  ticket_api_token?: string;

  notifications_enabled?: boolean;

  statuses?: string;
  ticket_limit?: string | number;
  poll_interval?: string | number;
  ticket_timeout?: string | number;

  group_webhook?: string;
  reply_bot_name?: string;

  users_default?: string;
  users_property?: string;
  users_cleaning?: string;
  users_police?: string;
  users_hospital?: string;
  users_community?: string;
  users_human_review?: string;

  export_dir?: string;
  routing_mode?: string;
  routing_confidence?: string | number;
  routing_timeout?: string | number;
}

const INPUT_TO_ENV: Record<keyof WeComSetupInput, EditableKey> = {
  ticket_api_url: 'REINS_TICKET_API_URL',
  ticket_api_token: 'REINS_TICKET_API_TOKEN',

  notifications_enabled: 'REINS_WECOM_NOTIFY_ENABLED',

  statuses: 'REINS_TICKET_API_STATUSES',
  ticket_limit: 'REINS_TICKET_API_LIMIT',
  poll_interval: 'REINS_TICKET_API_POLL_INTERVAL',
  ticket_timeout: 'REINS_TICKET_API_TIMEOUT',

  group_webhook: 'REINS_WECOM_NOTIFY_GROUP_WEBHOOK',
  reply_bot_name: 'REINS_WECOM_REPLY_BOT_NAME',

  users_default: 'REINS_WECOM_NOTIFY_USERS_DEFAULT',
  users_property: 'REINS_WECOM_NOTIFY_USERS_PROPERTY',
  users_cleaning: 'REINS_WECOM_NOTIFY_USERS_CLEANING',
  users_police: 'REINS_WECOM_NOTIFY_USERS_POLICE',
  users_hospital: 'REINS_WECOM_NOTIFY_USERS_HOSPITAL',
  users_community: 'REINS_WECOM_NOTIFY_USERS_COMMUNITY',
  users_human_review: 'REINS_WECOM_NOTIFY_USERS_HUMAN_REVIEW',

  export_dir: 'REINS_WECOM_EXPORT_DIR',
  routing_mode: 'REINS_WECOM_ROUTING_MODE',
  routing_confidence: 'REINS_WECOM_ROUTING_CONFIDENCE',
  routing_timeout: 'REINS_WECOM_ROUTING_TIMEOUT',
};

function envPath(): string {
  return join(resolveReinsHome(), '.env');
}

function cleanValue(value: unknown): string {
  const clean = String(value ?? '').trim();

  if (/\r|\n|\0/.test(clean)) {
    throw new Error('Configuration values must use one line');
  }

  return clean;
}

function booleanValue(value: string): boolean {
  const clean = value.trim().toLowerCase();

  return !['0', 'false', 'no', 'n', 'off', 'disabled'].includes(clean);
}

function notificationsEnabled(values: Map<string, string>): boolean {
  const explicit = values.get('REINS_WECOM_NOTIFY_ENABLED');

  // Notifications are OFF unless explicitly enabled.
  if (!explicit?.trim()) {
    return false;
  }

  return booleanValue(explicit);
}

function validateNumber(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
  integer = false,
): void {
  const clean = cleanValue(value);

  if (!clean) {
    return;
  }

  const parsed = Number(clean);

  if (
    !Number.isFinite(parsed) ||
    parsed < minimum ||
    parsed > maximum ||
    (integer && !Number.isInteger(parsed))
  ) {
    throw new Error(
      `${label} must be ${
        integer ? 'a whole number' : 'a number'
      } between ${minimum} and ${maximum}`,
    );
  }
}

function decodeEnvValue(value: string): string {
  const clean = value.trim();

  if (!clean) {
    return '';
  }

  if (
    (clean.startsWith('"') && clean.endsWith('"')) ||
    (clean.startsWith("'") && clean.endsWith("'"))
  ) {
    if (clean.startsWith('"')) {
      try {
        return JSON.parse(clean);
      } catch {
        return clean.slice(1, -1);
      }
    }

    return clean.slice(1, -1);
  }

  return clean;
}

function parseEnv(raw: string): Map<string, string> {
  const result = new Map<string, string>();

  for (const line of raw.split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line);

    if (match) {
      result.set(match[1], decodeEnvValue(match[2]));
    }
  }

  return result;
}

function serializeValue(value: string): string {
  return /^[A-Za-z0-9_./,:|?&=+%@~-]+$/.test(value)
    ? value
    : JSON.stringify(value);
}

async function readEnv(): Promise<{
  raw: string;
  values: Map<string, string>;
}> {
  let raw = '';

  try {
    raw = await readFile(envPath(), 'utf8');
  } catch (error: any) {
    if (error?.code !== 'ENOENT') {
      throw error;
    }
  }

  return {
    raw,
    values: parseEnv(raw),
  };
}

async function writeEnv(updates: Map<EditableKey, string>): Promise<void> {
  const { raw } = await readEnv();

  const remaining = new Map<EditableKey, string>(updates);
  const lines: string[] = [];

  for (const line of raw.split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=/.exec(line);
    const key = match?.[1] as EditableKey | undefined;

    if (!key || !remaining.has(key)) {
      if (line || lines.length) {
        lines.push(line);
      }

      continue;
    }

    const value = remaining.get(key) || '';

    if (value) {
      lines.push(`${key}=${serializeValue(value)}`);
    }

    remaining.delete(key);
  }

  if (lines.length && lines[lines.length - 1] !== '') {
    lines.push('');
  }

  for (const [key, value] of remaining) {
    if (value) {
      lines.push(`${key}=${serializeValue(value)}`);
    }
  }

  const target = envPath();

  await mkdir(dirname(target), {
    recursive: true,
  });

  const temporary = `${target}.tmp-${process.pid}`;

  await writeFile(
    temporary,
    `${lines.join('\n').replace(/\n+$/, '')}\n`,
    'utf8',
  );

  try {
    await chmod(temporary, 0o600);
  } catch {
    // Windows permissions are handled by the installer/runtime.
  }

  await rename(temporary, target);
}

function syncRuntimeEnv(updates: Map<EditableKey, string>): void {
  for (const [key, value] of updates) {
    if (value) {
      process.env[key] = value;
    } else {
      delete process.env[key];
    }
  }
}

function resolveReinsBin(): string {
  return (
    process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim() || 'reins'
  );
}

function parseCommandJson(raw: unknown): Record<string, any> {
  const text = String(raw ?? '').trim();

  if (!text) {
    return {};
  }

  try {
    const parsed = JSON.parse(text);

    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed;
    }

    return {};
  } catch {
    throw new Error(
      `Reins returned an invalid response: ${text.slice(0, 300)}`,
    );
  }
}

async function runReinsJson(args: string[]): Promise<Record<string, any>> {
  const home = resolveReinsHome();

  try {
    const { stdout } = await execFileAsync(resolveReinsBin(), args, {
      env: {
        ...process.env,

        REINS_HOME: home,
        HERMES_HOME: home,
      },

      encoding: 'utf8',
      maxBuffer: 4 * 1024 * 1024,
      timeout: 90_000,
      windowsHide: true,
    });

    return parseCommandJson(stdout);
  } catch (error: any) {
    let parsed: Record<string, any> = {};

    try {
      parsed = parseCommandJson(error?.stdout);
    } catch {
      // Fall through to stderr/message.
    }

    const detail =
      cleanValue(parsed?.error) ||
      cleanValue(error?.stderr) ||
      cleanValue(error?.message) ||
      'Reins command failed';

    throw new Error(detail);
  }
}

async function backgroundStatus(): Promise<Record<string, any>> {
  try {
    return await runReinsJson(['wecom', 'ticket-api', 'service', 'status']);
  } catch (error: any) {
    return {
      ok: false,
      installed: false,
      running: false,
      state: 'unknown',
      error:
        error?.message || 'Could not read background ticket service status',
    };
  }
}

function validateSetup(values: Map<string, string>): void {
  const url = values.get('REINS_TICKET_API_URL') || '';

  const token = values.get('REINS_TICKET_API_TOKEN') || '';

  const webhook = values.get('REINS_WECOM_NOTIFY_GROUP_WEBHOOK') || '';

  const recipient = values.get('REINS_WECOM_NOTIFY_USERS_DEFAULT') || '';

  const notifyEnabled = notificationsEnabled(values);

  if (!/^https:\/\//i.test(url)) {
    throw new Error('Ticket API URL must use HTTPS');
  }

  if (!token) {
    throw new Error('Ticket API token is required');
  }

  /*
   * Fetch-only mode.
   *
   * Ticket API is configured, so the poller may run.
   * No WeCom group webhook or recipient is required.
   */
  if (!notifyEnabled) {
    return;
  }

  /*
   * Notification mode.
   *
   * Only the computer responsible for group notifications
   * needs the webhook and recipient.
   */
  if (
    !/^https:\/\/qyapi\.weixin\.qq\.com\/cgi-bin\/webhook\/send\?key=/i.test(
      webhook,
    )
  ) {
    throw new Error('Enter a valid WeCom group robot webhook');
  }

  if (!recipient) {
    throw new Error('A default WeCom recipient UserID is required');
  }
}

function valueOrDefault(
  values: Map<string, string>,
  key: string,
  fallback: string,
): string {
  return values.get(key)?.trim() || fallback;
}

export async function getWeComSetupStatus(): Promise<Record<string, unknown>> {
  const { values } = await readEnv();

  const value = (key: EditableKey, fallback = ''): string =>
    values.get(key) || fallback;

  const notifyEnabled = notificationsEnabled(values);

  const ticketApiUrl = value(
    'REINS_TICKET_API_URL',
    'https://kf.lnluo.com/internal/tickets',
  );

  const ticketTokenConfigured = Boolean(value('REINS_TICKET_API_TOKEN'));

  const webhookConfigured = Boolean(value('REINS_WECOM_NOTIFY_GROUP_WEBHOOK'));

  const defaultRecipientConfigured = Boolean(
    value('REINS_WECOM_NOTIFY_USERS_DEFAULT'),
  );

  /*
   * configured = settings are valid.
   *
   * It does NOT mean the Windows/macOS background service is running.
   */
  const configured = Boolean(
    /^https:\/\//i.test(ticketApiUrl) &&
    ticketTokenConfigured &&
    (!notifyEnabled || (webhookConfigured && defaultRecipientConfigured)),
  );

  return {
    configured,

    ticket_api_token_configured: ticketTokenConfigured,

    group_webhook_configured: webhookConfigured,

    background: await backgroundStatus(),

    values: {
      ticket_api_url: ticketApiUrl,

      notifications_enabled: notifyEnabled,

      statuses: value(
        'REINS_TICKET_API_STATUSES',
        'pending_dispatch,dispatched,reopened,notification_failed',
      ),

      ticket_limit: value('REINS_TICKET_API_LIMIT', '20'),

      poll_interval: value('REINS_TICKET_API_POLL_INTERVAL', '30'),

      ticket_timeout: value('REINS_TICKET_API_TIMEOUT', '15'),

      reply_bot_name: value('REINS_WECOM_REPLY_BOT_NAME', '社区美女'),

      users_default: value('REINS_WECOM_NOTIFY_USERS_DEFAULT'),

      users_property: value('REINS_WECOM_NOTIFY_USERS_PROPERTY'),

      users_cleaning: value('REINS_WECOM_NOTIFY_USERS_CLEANING'),

      users_police: value('REINS_WECOM_NOTIFY_USERS_POLICE'),

      users_hospital: value('REINS_WECOM_NOTIFY_USERS_HOSPITAL'),

      users_community: value('REINS_WECOM_NOTIFY_USERS_COMMUNITY'),

      users_human_review: value('REINS_WECOM_NOTIFY_USERS_HUMAN_REVIEW'),

      export_dir: value('REINS_WECOM_EXPORT_DIR'),

      routing_mode: value('REINS_WECOM_ROUTING_MODE', 'hybrid'),

      routing_confidence: value('REINS_WECOM_ROUTING_CONFIDENCE', '0.85'),

      routing_timeout: value('REINS_WECOM_ROUTING_TIMEOUT', '15'),
    },
  };
}

/**
 * Start an already-configured ticket service.
 *
 * If the OS service has never been installed, install it first.
 *
 * On Windows this creates/starts:
 *   "Reins WeCom Ticket Poller"
 *
 * in Task Scheduler.
 */
export async function startWeComBackgroundService(): Promise<
  Record<string, unknown>
> {
  const { values } = await readEnv();

  validateSetup(values);

  const current = await backgroundStatus();

  let result: Record<string, any>;

  if (current?.installed) {
    result = await runReinsJson(['wecom', 'ticket-api', 'service', 'start']);
  } else {
    const interval = valueOrDefault(
      values,
      'REINS_TICKET_API_POLL_INTERVAL',
      '30',
    );

    result = await runReinsJson([
      'wecom',
      'ticket-api',
      'service',
      'install',
      '--interval',
      interval,
    ]);
  }

  if (!result?.ok || !result?.running) {
    throw new Error(
      result?.error || 'Reins could not start the background ticket service',
    );
  }

  return getWeComSetupStatus();
}

/**
 * Stop the background ticket poller.
 *
 * This does not delete the saved Ticket API settings.
 * On Windows the scheduled task remains installed and can
 * be started again later.
 */
export async function stopWeComBackgroundService(): Promise<
  Record<string, unknown>
> {
  const result = await runReinsJson(['wecom', 'ticket-api', 'service', 'stop']);

  if (!result?.ok) {
    throw new Error(
      result?.error || 'Reins could not stop the background ticket service',
    );
  }

  return getWeComSetupStatus();
}

/**
 * Save settings and install/restart the ticket poller.
 *
 * We intentionally use:
 *
 *   reins wecom ticket-api service install
 *
 * rather than:
 *
 *   reins bootstrap --enable-background-wecom
 *
 * because ticket fetching must be able to run without
 * a WeCom group notification webhook.
 */
export async function saveWeComSetup(
  input: WeComSetupInput,
): Promise<Record<string, unknown>> {
  validateNumber(input.ticket_limit, 'Ticket limit', 1, 100, true);

  validateNumber(input.poll_interval, 'Poll interval', 5, 86_400);

  validateNumber(input.ticket_timeout, 'Ticket API timeout', 1, 300);

  validateNumber(input.routing_confidence, 'Routing confidence', 0.5, 1);

  validateNumber(input.routing_timeout, 'Routing timeout', 2, 60);

  const { values: existing } = await readEnv();

  const updates = new Map<EditableKey, string>();

  /*
   * Always save the notification switch explicitly.
   *
   * If an old client does not provide the field,
   * notifications remain safely OFF.
   */
  updates.set(
    'REINS_WECOM_NOTIFY_ENABLED',
    input.notifications_enabled === true ? 'true' : 'false',
  );

  for (const [inputKey, envKey] of Object.entries(INPUT_TO_ENV) as Array<
    [keyof WeComSetupInput, EditableKey]
  >) {
    if (inputKey === 'notifications_enabled') {
      continue;
    }

    if (!(inputKey in input)) {
      continue;
    }

    const value = cleanValue(input[inputKey]);

    /*
     * A blank secret field means:
     * keep the existing saved secret.
     *
     * We never send the actual saved token/webhook
     * back to the Vue application.
     */
    if (SECRET_KEYS.has(envKey) && !value && existing.get(envKey)) {
      continue;
    }

    updates.set(envKey, value);
  }

  /*
   * Build the resulting settings in memory first
   * so we can validate before writing them.
   */
  const merged = new Map<string, string>(existing);

  for (const [key, value] of updates) {
    if (value) {
      merged.set(key, value);
    } else {
      merged.delete(key);
    }
  }

  /*
   * This is the critical behavior:
   *
   * notifications_enabled=false:
   *   Ticket URL required
   *   Ticket token required
   *   Webhook NOT required
   *   Recipient NOT required
   */
  validateSetup(merged);

  await writeEnv(updates);

  /*
   * The desktop Node backend stays alive for the entire
   * Tauri session. Keep its environment synchronized
   * with the settings we just wrote.
   */
  syncRuntimeEnv(updates);

  const interval = valueOrDefault(
    merged,
    'REINS_TICKET_API_POLL_INTERVAL',
    '30',
  );

  /*
   * "service install" is intentionally used here even
   * if already installed.
   *
   * On Windows ticket_service.py stops the existing
   * scheduled task, updates it and starts it again.
   *
   * Therefore changes to notification mode/settings
   * take effect immediately.
   */
  const result = await runReinsJson([
    'wecom',
    'ticket-api',
    'service',
    'install',
    '--interval',
    interval,
  ]);

  if (!result?.ok || !result?.running) {
    throw new Error(
      result?.error || 'Reins could not start the background ticket service',
    );
  }

  return getWeComSetupStatus();
}
