import { execFile } from 'child_process'
import { chmod, readFile, rename, writeFile } from 'fs/promises'
import { dirname, join } from 'path'
import { mkdir } from 'fs/promises'
import { promisify } from 'util'
import { resolveReinsHome } from './reins-path'

const execFileAsync = promisify(execFile)

const EDITABLE_KEYS = [
  'REINS_TICKET_API_URL',
  'REINS_TICKET_API_TOKEN',
  'REINS_TICKET_API_STATUSES',
  'REINS_TICKET_API_LIMIT',
  'REINS_TICKET_API_POLL_INTERVAL',
  'REINS_TICKET_API_TIMEOUT',
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
] as const

type EditableKey = typeof EDITABLE_KEYS[number]

const SECRET_KEYS = new Set<EditableKey>([
  'REINS_TICKET_API_TOKEN',
  'REINS_WECOM_NOTIFY_GROUP_WEBHOOK',
])

export interface WeComSetupInput {
  ticket_api_url?: string
  ticket_api_token?: string
  statuses?: string
  ticket_limit?: string | number
  poll_interval?: string | number
  ticket_timeout?: string | number
  group_webhook?: string
  reply_bot_name?: string
  users_default?: string
  users_property?: string
  users_cleaning?: string
  users_police?: string
  users_hospital?: string
  users_community?: string
  users_human_review?: string
  export_dir?: string
  routing_mode?: string
  routing_confidence?: string | number
  routing_timeout?: string | number
}

const INPUT_TO_ENV: Record<keyof WeComSetupInput, EditableKey> = {
  ticket_api_url: 'REINS_TICKET_API_URL',
  ticket_api_token: 'REINS_TICKET_API_TOKEN',
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
}

function envPath(): string {
  return join(resolveReinsHome(), '.env')
}

function cleanValue(value: unknown): string {
  const clean = String(value ?? '').trim()
  if (/\r|\n|\0/.test(clean)) throw new Error('Configuration values must use one line')
  return clean
}

function validateNumber(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
  integer = false,
): void {
  const clean = cleanValue(value)
  if (!clean) return
  const parsed = Number(clean)
  if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum || (integer && !Number.isInteger(parsed))) {
    throw new Error(`${label} must be ${integer ? 'a whole number' : 'a number'} between ${minimum} and ${maximum}`)
  }
}

function decodeEnvValue(value: string): string {
  const clean = value.trim()
  if (!clean) return ''
  if ((clean.startsWith('"') && clean.endsWith('"')) || (clean.startsWith("'") && clean.endsWith("'"))) {
    if (clean.startsWith('"')) {
      try { return JSON.parse(clean) } catch { return clean.slice(1, -1) }
    }
    return clean.slice(1, -1)
  }
  return clean
}

function parseEnv(raw: string): Map<string, string> {
  const result = new Map<string, string>()
  for (const line of raw.split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/.exec(line)
    if (match) result.set(match[1], decodeEnvValue(match[2]))
  }
  return result
}

function serializeValue(value: string): string {
  return /^[A-Za-z0-9_./,:|?&=+%@~-]+$/.test(value) ? value : JSON.stringify(value)
}

async function readEnv(): Promise<{ raw: string; values: Map<string, string> }> {
  let raw = ''
  try { raw = await readFile(envPath(), 'utf8') } catch (error: any) {
    if (error?.code !== 'ENOENT') throw error
  }
  return { raw, values: parseEnv(raw) }
}

async function writeEnv(updates: Map<EditableKey, string>): Promise<void> {
  const { raw } = await readEnv()
  const remaining = new Map(updates)
  const lines: string[] = []

  for (const line of raw.split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=/.exec(line)
    const key = match?.[1] as EditableKey | undefined
    if (!key || !remaining.has(key)) {
      if (line || lines.length) lines.push(line)
      continue
    }
    const value = remaining.get(key) || ''
    if (value) lines.push(`${key}=${serializeValue(value)}`)
    remaining.delete(key)
  }

  if (lines.length && lines[lines.length - 1] !== '') lines.push('')
  for (const [key, value] of remaining) {
    if (value) lines.push(`${key}=${serializeValue(value)}`)
  }

  const target = envPath()
  await mkdir(dirname(target), { recursive: true })
  const temporary = `${target}.tmp-${process.pid}`
  await writeFile(temporary, `${lines.join('\n').replace(/\n+$/, '')}\n`, 'utf8')
  try { await chmod(temporary, 0o600) } catch { /* Windows ACLs are applied by the installer. */ }
  await rename(temporary, target)
}

function resolveReinsBin(): string {
  return process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim() || 'reins'
}

async function runBootstrap(): Promise<any> {
  const home = resolveReinsHome()
  const { stdout } = await execFileAsync(
    resolveReinsBin(),
    ['bootstrap', '--enable-background-wecom', '--json'],
    {
      env: { ...process.env, REINS_HOME: home, HERMES_HOME: home },
      encoding: 'utf8',
      maxBuffer: 4 * 1024 * 1024,
      timeout: 90_000,
      windowsHide: true,
    },
  )
  return JSON.parse(String(stdout || '{}'))
}

export async function getWeComSetupStatus(): Promise<Record<string, unknown>> {
  const { values } = await readEnv()
  const value = (key: EditableKey, fallback = '') => values.get(key) || fallback
  const requiredConfigured = Boolean(
    value('REINS_TICKET_API_TOKEN')
    && value('REINS_WECOM_NOTIFY_GROUP_WEBHOOK')
    && value('REINS_WECOM_NOTIFY_USERS_DEFAULT'),
  )
  return {
    configured: requiredConfigured,
    ticket_api_token_configured: Boolean(value('REINS_TICKET_API_TOKEN')),
    group_webhook_configured: Boolean(value('REINS_WECOM_NOTIFY_GROUP_WEBHOOK')),
    values: {
      ticket_api_url: value('REINS_TICKET_API_URL', 'https://kf.lnluo.com/internal/tickets'),
      statuses: value('REINS_TICKET_API_STATUSES', 'pending_dispatch,dispatched,reopened,notification_failed'),
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
  }
}

export async function saveWeComSetup(input: WeComSetupInput): Promise<Record<string, unknown>> {
  validateNumber(input.ticket_limit, 'Ticket limit', 1, 100, true)
  validateNumber(input.poll_interval, 'Poll interval', 5, 86_400)
  validateNumber(input.ticket_timeout, 'Ticket API timeout', 1, 300)
  validateNumber(input.routing_confidence, 'Routing confidence', 0.5, 1)
  validateNumber(input.routing_timeout, 'Routing timeout', 2, 60)

  const { values: existing } = await readEnv()
  const updates = new Map<EditableKey, string>()
  for (const [inputKey, envKey] of Object.entries(INPUT_TO_ENV) as Array<[keyof WeComSetupInput, EditableKey]>) {
    if (!(inputKey in input)) continue
    const value = cleanValue(input[inputKey])
    if (SECRET_KEYS.has(envKey) && !value && existing.get(envKey)) continue
    updates.set(envKey, value)
  }

  const url = updates.get('REINS_TICKET_API_URL') || existing.get('REINS_TICKET_API_URL') || ''
  const token = updates.get('REINS_TICKET_API_TOKEN') || existing.get('REINS_TICKET_API_TOKEN') || ''
  const webhook = updates.get('REINS_WECOM_NOTIFY_GROUP_WEBHOOK') || existing.get('REINS_WECOM_NOTIFY_GROUP_WEBHOOK') || ''
  const recipient = updates.get('REINS_WECOM_NOTIFY_USERS_DEFAULT') || existing.get('REINS_WECOM_NOTIFY_USERS_DEFAULT') || ''
  if (!/^https:\/\//i.test(url)) throw new Error('Ticket API URL must use HTTPS')
  if (!token) throw new Error('Ticket API token is required')
  if (!/^https:\/\/qyapi\.weixin\.qq\.com\/cgi-bin\/webhook\/send\?key=/i.test(webhook)) {
    throw new Error('Enter a valid WeCom group robot webhook')
  }
  if (!recipient) throw new Error('A default WeCom recipient UserID is required')

  await writeEnv(updates)
  const product = await runBootstrap()
  if (!product?.wecom?.configured) throw new Error('WeCom configuration could not be validated')
  if (!product?.wecom?.background?.ok || !product?.wecom?.background?.running) {
    throw new Error('Reins could not start the WeCom background service. Restart Reins and try again.')
  }
  return {
    ...(await getWeComSetupStatus()),
    background: product.wecom.background,
  }
}
