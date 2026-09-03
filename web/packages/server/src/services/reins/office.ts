import { spawn, type ChildProcess } from 'child_process'
import { randomUUID } from 'crypto'
import { once } from 'events'
import { existsSync } from 'fs'
import { delimiter, resolve } from 'path'
import {
  officeCreationNeedsClarification,
  officeRevisionNeedsClarification,
} from './office-clarification'
import { resolveReinsHome } from './reins-path'
import { resolveReinsWorkspaceRoot } from './workspace-path'

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
  skill_id?: string
  presentation?: OfficePresentationOptions
}

export interface OfficeRevisionRequest {
  instruction: string
}

export interface OfficeImportRequest {
  format: OfficeFormat
  source_path: string
  file_name: string
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
  command_count: number
  metadata: Record<string, unknown>
}

export interface OfficeSkillDto {
  id: string
  format: OfficeFormat
  label_zh: string
  label_en: string
  description_zh: string
  description_en: string
  placeholder_zh: string
  placeholder_en: string
  defaults: Record<string, unknown>
}

export type OfficeOperationKind = 'create' | 'revise'
export type OfficeOperationStatus = 'queued' | 'running' | 'needs_input' | 'completed' | 'failed' | 'cancelled'

export interface OfficeProgressEventDto {
  stage: string
  percent: number
  message_zh: string
  message_en: string
  at: string
}

export interface OfficeOperationErrorDto {
  code: string
  title_zh: string
  title_en: string
  message_zh: string
  message_en: string
  suggestion_zh: string
  suggestion_en: string
  technical_detail: string
  retryable: boolean
}

export interface OfficeOperationClarificationDto {
  title_zh: string
  title_en: string
  message_zh: string
  message_en: string
  example_zh: string
  example_en: string
}

export interface OfficeOperationDto {
  id: string
  kind: OfficeOperationKind
  status: OfficeOperationStatus
  percent: number
  created_at: string
  updated_at: string
  events: OfficeProgressEventDto[]
  document?: OfficeDocumentDto
  clarification?: OfficeOperationClarificationDto
  error?: OfficeOperationErrorDto
}

export interface OfficeWorkerProgress {
  stage: string
  percent: number
  message_zh: string
  message_en: string
}

export interface OfficeChatIntentDecision {
  intent: 'revise' | 'create' | 'chat'
  format?: OfficeFormat
  confidence: number
}

const OFFICE_FORMATS = new Set<OfficeFormat>(['docx', 'xlsx', 'pptx'])
const OFFICE_TASK_SAFETY_TIMEOUT_MS = 30 * 60 * 1000
const DEFAULT_TIMEOUT_MS = Number(process.env.REINS_OFFICE_WEB_TIMEOUT_MS || '') || OFFICE_TASK_SAFETY_TIMEOUT_MS
const DEFAULT_CREATE_MODEL_TIMEOUT_SECONDS = Math.min(
  Math.max(Number(process.env.REINS_OFFICE_CONTENT_TIMEOUT_SECONDS || '') || 1_200, 60),
  1_500,
)
const DEFAULT_CREATE_WORKER_TIMEOUT_MS = Math.min(
  Math.max(
    Number(process.env.REINS_OFFICE_CREATE_WORKER_TIMEOUT_MS || '')
      || OFFICE_TASK_SAFETY_TIMEOUT_MS,
    180_000,
  ),
  3_600_000,
)
const DEFAULT_REVISION_MODEL_TIMEOUT_SECONDS = Math.min(
  Math.max(Number(process.env.REINS_OFFICE_REVISION_TIMEOUT_SECONDS || '') || 1_200, 30),
  1_500,
)
const DEFAULT_REVISION_WORKER_TIMEOUT_MS = Math.min(
  Math.max(
    Number(process.env.REINS_OFFICE_REVISION_WORKER_TIMEOUT_MS || '')
      || OFFICE_TASK_SAFETY_TIMEOUT_MS,
    180_000,
  ),
  3_600_000,
)
const OFFICE_PROGRESS_PREFIX = 'REINS_OFFICE_PROGRESS '
const OFFICE_OPERATION_TTL_MS = 60 * 60 * 1000
const officeOperations = new Map<string, OfficeOperationDto>()
const officeOperationControllers = new Map<string, AbortController>()

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
    language: optionalText(input.language, 'Language', 20) || 'zh',
    skill_id: optionalText(input.skill_id || input.skillId, 'Office skill', 120),
    ...(format === 'pptx' ? { presentation: normalizePresentationOptions(input.presentation) } : {}),
  }
}

export function normalizeOfficeRevisionRequest(body: unknown): OfficeRevisionRequest {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  return {
    instruction: requiredText(input.instruction || input.prompt, 'Office revision instruction', 30_000),
  }
}

export function normalizeOfficeImportRequest(
  formatValue: unknown,
  sourcePathValue: unknown,
  fileNameValue: unknown,
): OfficeImportRequest {
  const format = normalizeFormat(formatValue)
  const sourcePath = requiredText(sourcePathValue, 'Office import path', 4096)
  const rawName = requiredText(fileNameValue, 'Office import file name', 260)
  const fileName = rawName.replace(/\\/g, '/').split('/').pop()?.trim() || ''
  const expectedSuffix = `.${format}`
  if (!fileName || !fileName.toLowerCase().endsWith(expectedSuffix)) {
    throw serviceError(
      `The ${format.toUpperCase()} section only accepts ${expectedSuffix} files.`,
      'invalid_request',
    )
  }
  return { format, source_path: sourcePath, file_name: fileName }
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

function normalizeWorkerProgress(value: unknown): OfficeWorkerProgress | null {
  if (!value || typeof value !== 'object') return null
  const input = value as Record<string, unknown>
  const stage = String(input.stage || '').trim()
  const messageZh = String(input.message_zh || '').trim()
  const messageEn = String(input.message_en || '').trim()
  const parsedPercent = Number(input.percent)
  if (!stage || (!messageZh && !messageEn)) return null
  return {
    stage,
    percent: Number.isFinite(parsedPercent) ? Math.min(Math.max(Math.round(parsedPercent), 0), 100) : 0,
    message_zh: messageZh || messageEn,
    message_en: messageEn || messageZh,
  }
}

function parseProgressLine(line: string): OfficeWorkerProgress | null {
  const text = String(line || '').trim()
  if (!text.startsWith(OFFICE_PROGRESS_PREFIX)) return null
  try {
    return normalizeWorkerProgress(JSON.parse(text.slice(OFFICE_PROGRESS_PREFIX.length)))
  } catch {
    return null
  }
}

function terminateOfficeWorker(child: ChildProcess, signal: NodeJS.Signals) {
  if (process.platform === 'win32' && child.pid) {
    try {
      const killer = spawn(
        'taskkill',
        ['/PID', String(child.pid), '/T', ...(signal === 'SIGKILL' ? ['/F'] : [])],
        { windowsHide: true, stdio: 'ignore' },
      )
      killer.on('error', () => {
        try { child.kill(signal) } catch {}
      })
      killer.unref()
      return
    } catch {}
  }
  if (process.platform !== 'win32' && child.pid) {
    try {
      process.kill(-child.pid, signal)
      return
    } catch {}
  }
  try {
    child.kill(signal)
  } catch {}
}

async function runReinsOfficeJson(
  args: string[],
  {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    allowNonZero = false,
    onProgress,
    signal,
  }: {
    timeoutMs?: number
    allowNonZero?: boolean
    onProgress?: (progress: OfficeWorkerProgress) => void
    signal?: AbortSignal
  } = {},
): Promise<Record<string, unknown>> {
  if (signal?.aborted) {
    throw serviceError('Office processing cancelled by user.', 'worker_cancelled')
  }
  const reinsHome = resolveReinsHome()
  const invocation = resolveReinsInvocation()
  const child = spawn(invocation.command, [...invocation.argsPrefix, ...args], {
    cwd: invocation.cwd,
    env: {
      ...process.env,
      REINS_HOME: reinsHome,
      HERMES_HOME: process.env.HERMES_HOME?.trim() || reinsHome,
      REINS_WORKSPACE_ROOT: resolveReinsWorkspaceRoot(),
      ...(invocation.pythonPath
        ? { PYTHONPATH: [invocation.pythonPath, process.env.PYTHONPATH].filter(Boolean).join(delimiter) }
        : {}),
    },
    detached: process.platform !== 'win32',
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  let stdout = ''
  let stderr = ''
  let stderrBuffer = ''
  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')
  child.stdout.on('data', chunk => { stdout += chunk })
  const handleStderrLine = (line: string) => {
    const progress = parseProgressLine(line)
    if (progress) {
      try {
        onProgress?.(progress)
      } catch {}
      return
    }
    if (line.trim()) stderr += `${line}\n`
  }
  child.stderr.on('data', chunk => {
    stderrBuffer += String(chunk)
    const lines = stderrBuffer.split(/\r?\n/)
    stderrBuffer = lines.pop() || ''
    for (const line of lines) handleStderrLine(line)
  })

  let forceKillTimer: NodeJS.Timeout | undefined
  let timeoutTimer: NodeJS.Timeout | undefined
  let terminatedEarly = false
  const terminate = () => {
    if (terminatedEarly) return
    terminatedEarly = true
    terminateOfficeWorker(child, 'SIGTERM')
    forceKillTimer = setTimeout(() => terminateOfficeWorker(child, 'SIGKILL'), 2_000)
    forceKillTimer.unref()
  }
  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    timeoutTimer = setTimeout(() => {
      terminate()
      reject(serviceError(`Office processing timed out after ${Math.ceil(timeoutMs / 1000)} seconds.`, 'worker_timeout'))
    }, timeoutMs)
  })
  let abortHandler: (() => void) | undefined
  const abortPromise = new Promise<never>((_resolve, reject) => {
    if (!signal) return
    abortHandler = () => {
      terminate()
      reject(serviceError('Office processing cancelled by user.', 'worker_cancelled'))
    }
    if (signal.aborted) abortHandler()
    else signal.addEventListener('abort', abortHandler, { once: true })
  })
  try {
    const closePromise = once(child, 'close') as Promise<[number | null, NodeJS.Signals | null]>
    const errorPromise = once(child, 'error').then(([error]) => { throw error as Error })
    const [code] = await Promise.race([closePromise, errorPromise, timeoutPromise, abortPromise])
    if (stderrBuffer) {
      handleStderrLine(stderrBuffer)
      stderrBuffer = ''
    }
    const payload = parseJsonOutput(stdout)
    if (!allowNonZero && code !== 0) {
      const message = String(payload.error || stderr.trim() || `Office worker exited ${code}`)
      const error = serviceError(message, 'worker_error') as Error & {
        code: string
        workerErrorType?: string
      }
      error.workerErrorType = String(payload.error_type || '')
      throw error
    }
    return payload
  } finally {
    if (timeoutTimer) clearTimeout(timeoutTimer)
    if (signal && abortHandler) signal.removeEventListener('abort', abortHandler)
    if (!terminatedEarly && forceKillTimer) clearTimeout(forceKillTimer)
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
    command_count: Number(document.command_count || 0),
    metadata: document.metadata && typeof document.metadata === 'object'
      ? document.metadata as Record<string, unknown>
      : {},
  }
}

function normalizeSkill(value: unknown): OfficeSkillDto {
  if (!value || typeof value !== 'object') {
    throw serviceError('Office worker returned an invalid skill.', 'worker_error')
  }
  const skill = value as Record<string, unknown>
  return {
    id: requiredText(skill.id, 'Office skill id', 120),
    format: normalizeFormat(skill.format),
    label_zh: String(skill.label_zh || ''),
    label_en: String(skill.label_en || ''),
    description_zh: String(skill.description_zh || ''),
    description_en: String(skill.description_en || ''),
    placeholder_zh: String(skill.placeholder_zh || ''),
    placeholder_en: String(skill.placeholder_en || ''),
    defaults: skill.defaults && typeof skill.defaults === 'object'
      ? skill.defaults as Record<string, unknown>
      : {},
  }
}

export async function createOfficeDocument(
  input: OfficeCreateRequest,
  onProgress?: (progress: OfficeWorkerProgress) => void,
  signal?: AbortSignal,
): Promise<OfficeDocumentDto> {
  const args = [
    'office',
    'create',
    '--format',
    input.format,
    '--prompt',
    input.prompt,
    '--language',
    input.language,
    '--timeout',
    String(DEFAULT_CREATE_MODEL_TIMEOUT_SECONDS),
    '--json',
  ]
  if (onProgress) args.push('--progress')
  if (input.title) args.push('--title', input.title)
  if (input.skill_id) args.push('--skill', input.skill_id)
  if (input.format === 'pptx' && input.presentation) {
    args.push(
      '--ppt-style', input.presentation.style,
      '--slide-count', String(input.presentation.slide_count),
      '--audience', input.presentation.audience,
      '--detail', input.presentation.detail,
    )
  }

  const payload = await runReinsOfficeJson(args, {
    timeoutMs: DEFAULT_CREATE_WORKER_TIMEOUT_MS,
    onProgress,
    signal,
  })
  if (payload.ok === false) {
    throw serviceError(String(payload.error || 'Office creation failed.'), 'worker_error')
  }
  return normalizeDocument(payload.document)
}

export async function importOfficeDocument(
  formatValue: unknown,
  sourcePathValue: unknown,
  fileNameValue: unknown,
): Promise<OfficeDocumentDto> {
  const input = normalizeOfficeImportRequest(formatValue, sourcePathValue, fileNameValue)
  const payload = await runReinsOfficeJson([
    'office',
    'import',
    '--format', input.format,
    '--source', input.source_path,
    '--name', input.file_name,
    '--json',
  ], { timeoutMs: 180_000 })
  if (payload.ok === false) {
    throw serviceError(String(payload.error || 'Office import failed.'), 'worker_error')
  }
  return normalizeDocument(payload.document)
}

export async function reviseOfficeDocument(
  documentId: string,
  input: OfficeRevisionRequest,
  onProgress?: (progress: OfficeWorkerProgress) => void,
  signal?: AbortSignal,
): Promise<OfficeDocumentDto> {
  const id = requiredText(documentId, 'Office document id', 200)
  const payload = await runReinsOfficeJson([
    'office',
    'revise',
    '--id',
    id,
    '--instruction',
    input.instruction,
    '--timeout',
    String(DEFAULT_REVISION_MODEL_TIMEOUT_SECONDS),
    '--json',
    ...(onProgress ? ['--progress'] : []),
  ], { timeoutMs: DEFAULT_REVISION_WORKER_TIMEOUT_MS, onProgress, signal })
  if (payload.ok === false) {
    throw serviceError(String(payload.error || 'Office revision failed.'), 'worker_error')
  }
  return normalizeDocument(payload.document)
}

export async function classifyOfficeChatIntent(
  message: string,
  document: OfficeDocumentDto,
): Promise<OfficeChatIntentDecision> {
  const payload = await runReinsOfficeJson([
    'office',
    'route',
    '--message',
    requiredText(message, 'Office chat message', 30_000),
    '--document-title',
    requiredText(document.title || document.file_name, 'Office document title', 180),
    '--document-kind',
    document.kind,
    '--timeout',
    '45',
    '--json',
  ], { timeoutMs: 60_000 })
  if (payload.ok === false || !payload.decision || typeof payload.decision !== 'object') {
    throw serviceError(String(payload.error || 'Reins could not route the Office request.'), 'worker_error')
  }

  const decision = payload.decision as Record<string, unknown>
  const rawIntent = String(decision.intent || 'chat').trim().toLowerCase()
  const intent: OfficeChatIntentDecision['intent'] = (
    rawIntent === 'revise' || rawIntent === 'create' ? rawIntent : 'chat'
  )
  const parsedConfidence = Number(decision.confidence || 0)
  let format: OfficeFormat | undefined
  if (intent === 'create' && decision.format) {
    try {
      format = normalizeFormat(decision.format)
    } catch {}
  }
  return {
    intent,
    ...(intent === 'create' && format ? { format } : {}),
    confidence: Number.isFinite(parsedConfidence)
      ? Math.min(Math.max(parsedConfidence, 0), 1)
      : 0,
  }
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

export async function listOfficeSkills(format?: unknown): Promise<OfficeSkillDto[]> {
  const args = ['office', 'skills', '--json']
  if (String(format || '').trim()) args.push('--format', normalizeFormat(format))
  const payload = await runReinsOfficeJson(args, { timeoutMs: 30_000 })
  const skills = Array.isArray(payload.skills) ? payload.skills : []
  return skills.map(normalizeSkill)
}

export async function getOfficeStatus(): Promise<Record<string, unknown>> {
  const payload = await runReinsOfficeJson(
    ['office', 'doctor', '--json'],
    { timeoutMs: 30_000, allowNonZero: true },
  )
  const available = Boolean(payload.available)
  const reinsAvailable = Boolean(payload.reins_available)
  return {
    available,
    reins_available: reinsAvailable,
    documents: Number(payload.documents || 0),
    error: available && reinsAvailable ? null : 'Reins Office support is unavailable.',
    setup_hint: 'Restart Reins or reinstall the desktop app.',
  }
}

function nowIso(): string {
  return new Date().toISOString()
}

function pruneOfficeOperations() {
  const cutoff = Date.now() - OFFICE_OPERATION_TTL_MS
  for (const [id, operation] of officeOperations) {
    const updatedAt = new Date(operation.updated_at).getTime()
    if (Number.isFinite(updatedAt) && updatedAt < cutoff) {
      officeOperations.delete(id)
      officeOperationControllers.delete(id)
    }
  }
}

function operationSnapshot(operation: OfficeOperationDto): OfficeOperationDto {
  return {
    ...operation,
    events: operation.events.map(event => ({ ...event })),
    ...(operation.document ? { document: { ...operation.document } } : {}),
    ...(operation.clarification ? { clarification: { ...operation.clarification } } : {}),
    ...(operation.error ? { error: { ...operation.error } } : {}),
  }
}

function appendOperationProgress(operation: OfficeOperationDto, progress: OfficeWorkerProgress) {
  const event: OfficeProgressEventDto = { ...progress, at: nowIso() }
  const existingIndex = operation.events.findIndex(item => item.stage === event.stage)
  if (existingIndex >= 0) operation.events[existingIndex] = event
  else operation.events.push(event)
  operation.percent = Math.max(operation.percent, event.percent)
  operation.updated_at = event.at
}

function cleanTechnicalDetail(value: unknown): string {
  const raw = String(value || '')
  if (/TimeoutExpired:\s*Command\s*["']?\[/i.test(raw)) {
    return 'Reins content planning timed out before returning a result.'
  }
  const text = raw
    .replace(/\u001b\[[0-9;]*m/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return text.slice(0, 1800)
}

export function friendlyOfficeOperationError(
  error: unknown,
  kind: OfficeOperationKind,
  stage = '',
): OfficeOperationErrorDto {
  const input = error as { code?: string, message?: string, workerErrorType?: string }
  const code = String(input?.code || 'worker_error')
  const workerErrorType = String(input?.workerErrorType || '').toLowerCase()
  const detail = cleanTechnicalDetail(input?.message || error)
  const normalized = detail.toLowerCase()

  if (
    code === 'worker_timeout'
    || workerErrorType.includes('timeout')
    || normalized.includes('timed out')
    || normalized.includes('timeout')
  ) {
    return {
      code: 'timeout',
      title_zh: '处理时间过长',
      title_en: 'Office operation timed out',
      message_zh: kind === 'create' ? '文件未能在规定时间内完成生成。' : '文件未能在规定时间内完成修改。',
      message_en: `The document could not finish ${kind === 'create' ? 'generating' : 'revising'} within the time limit.`,
      suggestion_zh: '请确认模型连接正常后重试。无需重复补充相同内容；生成期间可随时取消，原文件不会因超时而丢失。',
      suggestion_en: 'Confirm the model connection and try again. You do not need to repeat the same details; generation can be cancelled at any time, and the original file is preserved.',
      technical_detail: detail,
      retryable: true,
    }
  }

  if (
    normalized.includes('winerror 32')
    || normalized.includes('sharing violation')
    || normalized.includes('being used by another program')
    || normalized.includes('used by another process')
    || normalized.includes('file is open in another')
    || normalized.includes('另一个程序正在使用此文件')
  ) {
    return {
      code: 'file_in_use',
      title_zh: '文件正在被占用',
      title_en: 'Office file is in use',
      message_zh: kind === 'revise'
        ? 'Windows 暂时无法替换正在使用的文件，原文件已保留。'
        : 'Windows 暂时无法写入正在使用的文件。',
      message_en: kind === 'revise'
        ? 'Windows could not replace the file while another program was using it. The original file was preserved.'
        : 'Windows could not write the file while another program was using it.',
      suggestion_zh: '请关闭 Microsoft Office 中的该文件，并关闭文件资源管理器预览窗格后重试。',
      suggestion_en: 'Close the file in Microsoft Office and turn off the File Explorer preview pane, then try again.',
      technical_detail: detail,
      retryable: true,
    }
  }

  if (
    normalized.includes('enoent')
    || normalized.includes('winerror 2')
    || normalized.includes('winerror 6')
    || normalized.includes('the handle is invalid')
    || normalized.includes('cannot find the file specified')
    || normalized.includes('could not start reins')
    || normalized.includes('failed to start reins')
    || normalized.includes('runtime is incomplete')
    || /\bspawn\s+[^\s]+/.test(normalized)
  ) {
    return {
      code: 'runtime_unavailable',
      title_zh: 'Office 服务暂时不可用',
      title_en: 'Office service is unavailable',
      message_zh: 'Reins 无法启动本机的 Office 内容生成服务。',
      message_en: 'Reins could not start the local Office content service.',
      suggestion_zh: '请完全退出并重新打开 Reins 后重试；如果问题仍然存在，请重新安装当前版本。',
      suggestion_en: 'Quit and reopen Reins, then try again. Reinstall the current version if the problem continues.',
      technical_detail: detail,
      retryable: true,
    }
  }

  if (
    normalized.includes('no llm provider configured')
    || normalized.includes('no provider credentials configured')
    || normalized.includes('no model configured')
    || normalized.includes('provider is not configured')
    || normalized.includes('provider not configured')
    || normalized.includes('missing api key')
    || normalized.includes('no api key found')
  ) {
    return {
      code: 'model_unavailable',
      title_zh: '尚未配置可用模型',
      title_en: 'No model is configured',
      message_zh: 'Reins Office 需要使用当前模型生成文件内容，但没有找到可用的模型连接。',
      message_en: 'Reins Office needs the current model to generate document content, but no usable model connection was found.',
      suggestion_zh: '请在模型设置中完成提供商、模型和密钥配置，然后重新生成。',
      suggestion_en: 'Configure a provider, model, and credentials in Model settings, then generate the file again.',
      technical_detail: detail,
      retryable: true,
    }
  }

  if (
    kind === 'create'
    && stage.includes('officecli_prepare')
    && (
      normalized.includes('could not find file')
      || normalized.includes('file not found')
      || normalized.includes('path not found')
    )
  ) {
    return {
      code: 'workspace_path_failed',
      title_zh: 'Windows 文件路径处理失败',
      title_en: 'Windows file path preparation failed',
      message_zh: '内容已经准备完成，但 Reins Office 未能在工作区准备目标文件。',
      message_en: 'The content was prepared, but Reins Office could not prepare the destination file in the workspace.',
      suggestion_zh: '请重新生成文件。Reins 会先使用兼容的临时路径生成并验证文件，再保存为中文文件名。',
      suggestion_en: 'Generate the file again. Reins will create and validate it through a compatible temporary path before publishing the Chinese filename.',
      technical_detail: detail,
      retryable: true,
    }
  }

  if (normalized.includes('not found') || normalized.includes('no longer exists')) {
    return {
      code: 'document_not_found',
      title_zh: '找不到原文件',
      title_en: 'Original file not found',
      message_zh: '要修改的 Office 文件已移动、删除或不再存在。',
      message_en: 'The Office file being revised was moved, deleted, or no longer exists.',
      suggestion_zh: '请从最近文件中重新选择有效文件，然后再次提交修改。',
      suggestion_en: 'Select an available file from Recent files and submit the revision again.',
      technical_detail: detail,
      retryable: false,
    }
  }

  if (
    stage.includes('content')
    || stage.includes('planning')
    || normalized.includes('reins failed to generate')
    || normalized.includes('json')
  ) {
    return {
      code: 'content_generation_failed',
      title_zh: kind === 'create' ? '内容生成失败' : '修改方案生成失败',
      title_en: kind === 'create' ? 'Content generation failed' : 'Revision planning failed',
      message_zh: 'Reins 未能生成可供 OfficeCLI 使用的有效内容结构。',
      message_en: 'Reins did not produce a valid content structure for OfficeCLI.',
      suggestion_zh: '请补充更明确的主题、数据或修改要求后重试，并确认当前模型连接正常。',
      suggestion_en: 'Add clearer topic, data, or revision requirements and confirm the model connection before retrying.',
      technical_detail: detail,
      retryable: true,
    }
  }

  if (
    stage.includes('officecli')
    || stage.includes('validat')
    || stage.includes('layout')
    || normalized.includes('officecli')
    || normalized.includes('layout issue')
  ) {
    if (kind === 'revise') {
      return {
        code: 'officecli_failed',
        title_zh: '文件修改未完成',
        title_en: 'Document revision did not complete',
        message_zh: '本次修改方案与原文件结构或格式不兼容，原文件已完整保留。',
        message_en: 'The revision plan was not compatible with the existing file structure or formatting. The original file was preserved.',
        suggestion_zh: '请直接重试相同要求。Reins 会重新读取当前文件的内容和样式，再通过 OfficeCLI 修改同一个文件。',
        suggestion_en: 'Retry the same request. Reins will reread the current content and styles, then revise the same file through OfficeCLI.',
        technical_detail: detail,
        retryable: true,
      }
    }
    return {
      code: 'officecli_failed',
      title_zh: '文件生成或验证失败',
      title_en: 'File rendering or validation failed',
      message_zh: '内容已经准备完成，但 OfficeCLI 未能生成通过检查的文件。',
      message_en: 'The content was prepared, but OfficeCLI could not produce a file that passed validation.',
      suggestion_zh: '请缩短过长内容、减少复杂版式后重试。演示文稿可尝试减少单页文字。',
      suggestion_en: 'Shorten long content or simplify the layout. For presentations, reduce text on each slide.',
      technical_detail: detail,
      retryable: true,
    }
  }

  return {
    code,
    title_zh: kind === 'create' ? '文件生成失败' : '文件修改失败',
    title_en: kind === 'create' ? 'Document creation failed' : 'Document revision failed',
    message_zh: kind === 'create' ? '本次 Office 文件生成未完成。' : '本次 Office 文件修改未完成，原文件已保留。',
    message_en: kind === 'create' ? 'The Office document was not created.' : 'The Office revision did not complete; the original file was preserved.',
    suggestion_zh: '请查看下方错误详情，调整要求后重试。',
    suggestion_en: 'Review the error detail below, adjust the request, and try again.',
    technical_detail: detail,
    retryable: code !== 'invalid_request',
  }
}

export function shouldAskForOfficeClarification(error: OfficeOperationErrorDto): boolean {
  if (error.code !== 'content_generation_failed') return false
  const detail = error.technical_detail.toLowerCase()
  return !/(?:timed out|connection|network|socket|api key|authentication|unauthorized|forbidden|quota|rate limit|model unavailable|provider unavailable|provider configured|model configured|credentials configured|enoent|winerror|spawn|runtime|python|permission|access denied)/.test(detail)
}

export function shouldRequestOfficeOperationClarification(
  error: OfficeOperationErrorDto,
  kind: OfficeOperationKind,
  requestText = '',
  skillId = '',
): boolean {
  if (!shouldAskForOfficeClarification(error)) return false
  if (kind === 'revise') return true
  if (skillId.trim()) return false
  return officeCreationNeedsClarification(requestText)
}

function createOperation(kind: OfficeOperationKind): OfficeOperationDto {
  pruneOfficeOperations()
  const timestamp = nowIso()
  const operation: OfficeOperationDto = {
    id: `office_op_${randomUUID()}`,
    kind,
    status: 'queued',
    percent: 0,
    created_at: timestamp,
    updated_at: timestamp,
    events: [],
  }
  officeOperations.set(operation.id, operation)
  return operation
}

function requestOperationClarification(operation: OfficeOperationDto) {
  const revising = operation.kind === 'revise'
  operation.status = 'needs_input'
  operation.error = undefined
  operation.clarification = revising
    ? {
        title_zh: '请补充具体修改要求',
        title_en: 'Please provide specific revision details',
        message_zh: '请说明要修改的部分、目标内容或样式，以及需要保留的内容。当前文件会保持不变。',
        message_en: 'Describe which section to change, the desired content or style, and what must remain unchanged. The current file will be preserved.',
        example_zh: '将标题改为红色，把第二部分扩写为三段，其他内容保持不变。',
        example_en: 'Make the title red, expand section two to three paragraphs, and keep everything else unchanged.',
      }
    : {
        title_zh: '请补充文件内容要求',
        title_en: 'Please provide more document details',
        message_zh: '请说明文件用途、必须包含的主要内容，以及期望的格式或风格。',
        message_en: 'Describe the document purpose, the main content it must include, and the format or style you prefer.',
        example_zh: '为社区居民制作防汛通知，包含准备事项、避险路线和联系人，语气正式简洁。',
        example_en: 'Create a concise formal flood-safety notice for residents, including preparation steps, evacuation routes, and contacts.',
      }
  appendOperationProgress(operation, {
    stage: 'needs_input',
    percent: operation.percent,
    message_zh: operation.clarification.title_zh,
    message_en: operation.clarification.title_en,
  })
}

function failOperation(
  operation: OfficeOperationDto,
  error: unknown,
  requestText = '',
  skillId = '',
) {
  if (operation.status === 'cancelled' || String((error as { code?: string })?.code || '') === 'worker_cancelled') {
    return
  }
  const lastStage = operation.events.at(-1)?.stage || ''
  const friendly = friendlyOfficeOperationError(error, operation.kind, lastStage)
  if (shouldRequestOfficeOperationClarification(
    friendly,
    operation.kind,
    requestText,
    skillId,
  )) {
    requestOperationClarification(operation)
    return
  }
  operation.status = 'failed'
  operation.error = friendly
  appendOperationProgress(operation, {
    stage: 'failed',
    percent: operation.percent,
    message_zh: operation.error.title_zh,
    message_en: operation.error.title_en,
  })
}

export function startOfficeCreateOperation(input: OfficeCreateRequest): OfficeOperationDto {
  const operation = createOperation('create')
  const controller = new AbortController()
  officeOperationControllers.set(operation.id, controller)
  queueMicrotask(() => {
    if (operation.status === 'cancelled') return
    operation.status = 'running'
    operation.updated_at = nowIso()
    void createOfficeDocument(input, progress => appendOperationProgress(operation, progress), controller.signal)
      .then(document => {
        if (operation.status === 'cancelled') return
        operation.document = document
        operation.status = 'completed'
        operation.percent = 100
        operation.updated_at = nowIso()
      })
      .catch(error => failOperation(operation, error, input.prompt, input.skill_id))
      .finally(() => officeOperationControllers.delete(operation.id))
  })
  return operationSnapshot(operation)
}

export function startOfficeRevisionOperation(
  documentId: string,
  input: OfficeRevisionRequest,
): OfficeOperationDto {
  const operation = createOperation('revise')
  if (officeRevisionNeedsClarification(input.instruction)) {
    requestOperationClarification(operation)
    return operationSnapshot(operation)
  }
  const controller = new AbortController()
  officeOperationControllers.set(operation.id, controller)
  queueMicrotask(() => {
    if (operation.status === 'cancelled') return
    operation.status = 'running'
    operation.updated_at = nowIso()
    void reviseOfficeDocument(
      documentId,
      input,
      progress => appendOperationProgress(operation, progress),
      controller.signal,
    )
      .then(document => {
        if (operation.status === 'cancelled') return
        operation.document = document
        operation.status = 'completed'
        operation.percent = 100
        operation.updated_at = nowIso()
      })
      .catch(error => failOperation(operation, error, input.instruction))
      .finally(() => officeOperationControllers.delete(operation.id))
  })
  return operationSnapshot(operation)
}

export function getOfficeOperation(operationId: string): OfficeOperationDto {
  pruneOfficeOperations()
  const id = requiredText(operationId, 'Office operation id', 200)
  const operation = officeOperations.get(id)
  if (!operation) throw serviceError('Office operation was not found or has expired.', 'not_found')
  return operationSnapshot(operation)
}

export function cancelOfficeOperation(operationId: string): OfficeOperationDto {
  pruneOfficeOperations()
  const id = requiredText(operationId, 'Office operation id', 200)
  const operation = officeOperations.get(id)
  if (!operation) throw serviceError('Office operation was not found or has expired.', 'not_found')
  if (operation.status !== 'queued' && operation.status !== 'running') {
    return operationSnapshot(operation)
  }

  operation.status = 'cancelled'
  appendOperationProgress(operation, {
    stage: 'cancelled',
    percent: operation.percent,
    message_zh: '任务已由用户取消',
    message_en: 'Task cancelled by the user',
  })
  officeOperationControllers.get(id)?.abort()
  officeOperationControllers.delete(id)
  return operationSnapshot(operation)
}
