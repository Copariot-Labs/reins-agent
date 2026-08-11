import { spawn } from 'child_process'
import { once } from 'events'
import { existsSync } from 'fs'
import { delimiter, resolve } from 'path'
import { resolveReinsHome } from './reins-path'

export type OfficeFormat = 'docx' | 'xlsx' | 'pptx'
export type OfficePresentationStyle = 'auto' | 'executive' | 'modern' | 'bold' | 'minimal'
export type OfficePresentationAudience = 'general' | 'executive' | 'client' | 'team'
export type OfficePresentationDetail = 'concise' | 'balanced' | 'detailed'

export interface OfficePresentationOptions {
  style: OfficePresentationStyle
  slide_count: number
  audience: OfficePresentationAudience
  detail: OfficePresentationDetail
}

export interface OfficeCreateRequest {
  format: OfficeFormat
  prompt: string
  title?: string
  language: string
  presentation?: OfficePresentationOptions
}

export interface OfficeRevisionRequest {
  instruction: string
}

export interface OfficeDocumentDto {
  id: string
  title: string
  kind: OfficeFormat
  path: string
  file_name: string
  mime_type: string
  created_at: string
  updated_at: string
  revision_count: number
  prompt: string
  generator: string
  officecli_bin: string | null
  command_count: number
  metadata: Record<string, unknown>
}

const OFFICE_FORMATS = new Set<OfficeFormat>(['docx', 'xlsx', 'pptx'])
const DEFAULT_TIMEOUT_MS = Number(process.env.REINS_OFFICE_WEB_TIMEOUT_MS || '') || 240_000

function serviceError(message: string, code: string): Error & { code: string } {
  return Object.assign(new Error(message), { code })
}

interface ReinsInvocation {
  command: string
  argsPrefix: string[]
  cwd?: string
  pythonPath?: string
}

function resolveReinsInvocation(): ReinsInvocation {
  const explicit = process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim()
  if (explicit) return { command: explicit, argsPrefix: [] }

  const roots = new Set([
    process.env.REINS_PROJECT_ROOT?.trim(),
    resolve(process.cwd(), '..'),
    process.cwd(),
  ].filter(Boolean) as string[])

  for (const root of roots) {
    const python = process.platform === 'win32'
      ? resolve(root, '.venv', 'Scripts', 'python.exe')
      : resolve(root, '.venv', 'bin', 'python')
    if (existsSync(python)) {
      return {
        command: python,
        argsPrefix: ['-m', 'reins.main'],
        cwd: root,
        pythonPath: resolve(root, 'src'),
      }
    }
  }

  return { command: 'reins', argsPrefix: [] }
}

function normalizeFormat(value: unknown): OfficeFormat {
  const text = String(value || 'docx').trim().toLowerCase()
  const aliases: Record<string, OfficeFormat> = {
    word: 'docx',
    doc: 'docx',
    docx: 'docx',
    excel: 'xlsx',
    xls: 'xlsx',
    xlsx: 'xlsx',
    sheet: 'xlsx',
    spreadsheet: 'xlsx',
    ppt: 'pptx',
    pptx: 'pptx',
    powerpoint: 'pptx',
    presentation: 'pptx',
  }
  const format = aliases[text] || text
  if (OFFICE_FORMATS.has(format as OfficeFormat)) return format as OfficeFormat
  throw serviceError('Invalid Office format.', 'invalid_request')
}

function requiredText(value: unknown, field: string, maxLength: number): string {
  const text = String(value || '').trim()
  if (!text) throw serviceError(`${field} is required.`, 'invalid_request')
  if (text.length > maxLength) {
    throw serviceError(`${field} cannot exceed ${maxLength} characters.`, 'invalid_request')
  }
  return text
}

function optionalText(value: unknown, field: string, maxLength: number): string | undefined {
  const text = String(value || '').trim()
  if (!text) return undefined
  if (text.length > maxLength) {
    throw serviceError(`${field} cannot exceed ${maxLength} characters.`, 'invalid_request')
  }
  return text
}

function enumValue<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  const normalized = String(value || '').trim().toLowerCase() as T
  return allowed.includes(normalized) ? normalized : fallback
}

function normalizePresentationOptions(value: unknown): OfficePresentationOptions {
  const input = value && typeof value === 'object' ? value as Record<string, unknown> : {}
  const parsedSlideCount = Number(input.slide_count || input.slideCount || 8)
  const slideCount = Number.isInteger(parsedSlideCount)
    ? Math.min(Math.max(parsedSlideCount, 5), 15)
    : 8
  return {
    style: enumValue(
      input.style,
      ['auto', 'executive', 'modern', 'bold', 'minimal'] as const,
      'auto',
    ),
    slide_count: slideCount,
    audience: enumValue(
      input.audience,
      ['general', 'executive', 'client', 'team'] as const,
      'general',
    ),
    detail: enumValue(
      input.detail,
      ['concise', 'balanced', 'detailed'] as const,
      'balanced',
    ),
  }
}

export function normalizeOfficeCreateRequest(body: unknown): OfficeCreateRequest {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const format = normalizeFormat(input.format || input.kind)
  return {
    format,
    prompt: requiredText(input.prompt, 'Office prompt', 30_000),
    title: optionalText(input.title, 'Title', 180),
    language: optionalText(input.language, 'Language', 20) || 'en',
    ...(format === 'pptx' ? { presentation: normalizePresentationOptions(input.presentation) } : {}),
  }
}

export function normalizeOfficeRevisionRequest(body: unknown): OfficeRevisionRequest {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  return {
    instruction: requiredText(input.instruction || input.prompt, 'Office revision instruction', 30_000),
  }
}

function parseJsonOutput(stdout: string): Record<string, unknown> {
  const text = String(stdout || '').trim()
  if (!text) throw serviceError('Office worker returned empty output.', 'worker_error')
  try {
    return JSON.parse(text) as Record<string, unknown>
  } catch {}

  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start >= 0 && end > start) {
    try {
      return JSON.parse(text.slice(start, end + 1)) as Record<string, unknown>
    } catch {}
  }

  throw serviceError('Office worker returned invalid JSON.', 'worker_error')
}

async function runReinsOfficeJson(
  args: string[],
  {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    allowNonZero = false,
  }: { timeoutMs?: number, allowNonZero?: boolean } = {},
): Promise<Record<string, unknown>> {
  const reinsHome = resolveReinsHome()
  const invocation = resolveReinsInvocation()
  const child = spawn(invocation.command, [...invocation.argsPrefix, ...args], {
    cwd: invocation.cwd,
    env: {
      ...process.env,
      REINS_HOME: reinsHome,
      HERMES_HOME: process.env.HERMES_HOME?.trim() || reinsHome,
      ...(invocation.pythonPath
        ? { PYTHONPATH: [invocation.pythonPath, process.env.PYTHONPATH].filter(Boolean).join(delimiter) }
        : {}),
    },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  let stdout = ''
  let stderr = ''
  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')
  child.stdout.on('data', chunk => { stdout += chunk })
  child.stderr.on('data', chunk => { stderr += chunk })

  let forceKillTimer: NodeJS.Timeout | undefined
  let timeoutTimer: NodeJS.Timeout | undefined
  let timedOut = false
  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    timeoutTimer = setTimeout(() => {
      timedOut = true
      child.kill('SIGTERM')
      forceKillTimer = setTimeout(() => child.kill('SIGKILL'), 2_000)
      forceKillTimer.unref()
      reject(serviceError(`Office processing timed out after ${Math.ceil(timeoutMs / 1000)} seconds.`, 'worker_timeout'))
    }, timeoutMs)
  })
  try {
    const closePromise = once(child, 'close') as Promise<[number | null, NodeJS.Signals | null]>
    const errorPromise = once(child, 'error').then(([error]) => { throw error as Error })
    const [code] = await Promise.race([closePromise, errorPromise, timeoutPromise])
    const payload = parseJsonOutput(stdout)
    if (!allowNonZero && code !== 0) {
      const message = String(payload.error || stderr.trim() || `Office worker exited ${code}`)
      throw serviceError(message, 'worker_error')
    }
    return payload
  } finally {
    if (timeoutTimer) clearTimeout(timeoutTimer)
    if (!timedOut && forceKillTimer) clearTimeout(forceKillTimer)
  }
}

function normalizeDocument(value: unknown): OfficeDocumentDto {
  if (!value || typeof value !== 'object') {
    throw serviceError('Office worker did not return a document.', 'worker_error')
  }
  const document = value as Record<string, unknown>
  const generator = String(document.generator || 'reins')
  return {
    id: String(document.id || ''),
    title: String(document.title || 'Office Document'),
    kind: normalizeFormat(document.kind),
    path: resolve(String(document.path || '')),
    file_name: String(document.file_name || ''),
    mime_type: String(document.mime_type || ''),
    created_at: String(document.created_at || ''),
    updated_at: String(document.updated_at || document.created_at || ''),
    revision_count: Number(document.revision_count || 0),
    prompt: String(document.prompt || ''),
    generator: generator.toLowerCase() === 'hermes' ? 'reins' : generator,
    officecli_bin: document.officecli_bin == null ? null : String(document.officecli_bin),
    command_count: Number(document.command_count || 0),
    metadata: document.metadata && typeof document.metadata === 'object'
      ? document.metadata as Record<string, unknown>
      : {},
  }
}

export async function createOfficeDocument(input: OfficeCreateRequest): Promise<OfficeDocumentDto> {
  const args = [
    'office',
    'create',
    '--format',
    input.format,
    '--prompt',
    input.prompt,
    '--language',
    input.language,
    '--json',
  ]
  if (input.title) args.push('--title', input.title)
  if (input.format === 'pptx' && input.presentation) {
    args.push(
      '--ppt-style', input.presentation.style,
      '--slide-count', String(input.presentation.slide_count),
      '--audience', input.presentation.audience,
      '--detail', input.presentation.detail,
    )
  }

  const payload = await runReinsOfficeJson(args)
  if (payload.ok === false) {
    throw serviceError(String(payload.error || 'Office creation failed.'), 'worker_error')
  }
  return normalizeDocument(payload.document)
}

export async function reviseOfficeDocument(
  documentId: string,
  input: OfficeRevisionRequest,
): Promise<OfficeDocumentDto> {
  const id = requiredText(documentId, 'Office document id', 200)
  const payload = await runReinsOfficeJson([
    'office',
    'revise',
    '--id',
    id,
    '--instruction',
    input.instruction,
    '--json',
  ], { timeoutMs: Math.max(DEFAULT_TIMEOUT_MS, 300_000) })
  if (payload.ok === false) {
    throw serviceError(String(payload.error || 'Office revision failed.'), 'worker_error')
  }
  return normalizeDocument(payload.document)
}

export async function getOfficePreviewPath(documentId: string): Promise<string> {
  const id = requiredText(documentId, 'Office document id', 200)
  const payload = await runReinsOfficeJson([
    'office',
    'preview',
    '--id',
    id,
    '--json',
  ], { timeoutMs: 120_000 })
  if (payload.ok === false || !payload.preview_path) {
    throw serviceError(String(payload.error || 'Office preview failed.'), 'worker_error')
  }
  return resolve(String(payload.preview_path))
}

export async function listOfficeDocuments(limit: unknown = 25): Promise<OfficeDocumentDto[]> {
  const parsedLimit = Number(limit || 25)
  const safeLimit = Number.isInteger(parsedLimit) && parsedLimit > 0
    ? Math.min(parsedLimit, 100)
    : 25
  const payload = await runReinsOfficeJson([
    'office',
    'list',
    '--limit',
    String(safeLimit),
    '--json',
  ])
  const docs = Array.isArray(payload.documents) ? payload.documents : []
  return docs.map(normalizeDocument)
}

export async function getOfficeStatus(): Promise<Record<string, unknown>> {
  return runReinsOfficeJson(['office', 'doctor', '--json'], { timeoutMs: 30_000, allowNonZero: true })
}
