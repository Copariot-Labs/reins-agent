import { spawn } from 'child_process'
import { randomBytes } from 'crypto'
import { once } from 'events'
import { createReadStream } from 'fs'
import { mkdir, readdir, readFile, realpath, rename, rm, stat, writeFile } from 'fs/promises'
import { basename, extname, isAbsolute, join, relative, resolve } from 'path'
import { resolveReinsHome } from './reins-path'

export type PresentationStyle = 'modern' | 'tech' | 'corporate' | 'creative' | 'minimal' | 'dark'
export type PresentationOutputFormat = 'pptx' | 'html' | 'pdf'
export type PresentationEngine = 'auto' | 'ppt_master' | 'frontend_slides' | 'native_pptx'
export type PresentationAction = 'new' | 'modify' | 'restyle' | 'convert'
export type PresentationSessionSourceType = 'prompt' | 'pptx' | 'pdf'

export interface PresentationSubmitRequest {
  action: PresentationAction
  prompt?: string
  source_path?: string
  instruction?: string
  title?: string
  audience?: string
  language: string
  slide_count: number
  style: PresentationStyle
  output_format: PresentationOutputFormat
  engine: PresentationEngine
  aspect_ratio: '16:9' | '4:3'
  run_qa: boolean
  maximum_qa_rounds: number
  metadata: Record<string, unknown>
}

export interface PresentationArtifactDto {
  kind: string
  file_name: string
  mime_type: string | null
}

export interface PresentationJobDto {
  job_id: string
  status: string
  progress: number
  phase: string
  action: string
  engine: string
  created_at: string
  updated_at: string
  error: string | null
  warnings: string[]
  artifacts: PresentationArtifactDto[]
  metadata: Record<string, unknown>
  has_output: boolean
  output_file_name: string | null
  preview_available: boolean
}

export interface PresentationMedia {
  stream: ReturnType<typeof createReadStream>
  fileName: string
  mime: string
  size: number
}

interface StoredPresentationTurn {
  turn: number
  action: PresentationAction
  instruction: string
  style: PresentationStyle
  output_format: PresentationOutputFormat
  job_id: string
  parent_revision: number
  advances_deck: boolean
  created_at: string
}

interface StoredPresentationSession {
  schema: 'reins_presentation_session.v1'
  session_id: string
  name: string
  source_file_name: string
  source_path: string | null
  source_type: PresentationSessionSourceType
  active_revision: number
  created_at: string
  updated_at: string
  turns: StoredPresentationTurn[]
}

export interface PresentationSessionTurnDto extends Omit<StoredPresentationTurn, 'job_id'> {
  job: PresentationJobDto
}

export interface PresentationSessionDto {
  session_id: string
  name: string
  source_file_name: string
  source_type: PresentationSessionSourceType
  deck_ready: boolean
  active_revision: number
  created_at: string
  updated_at: string
  turns: PresentationSessionTurnDto[]
}

const JOB_ID_PATTERN = /^ppt_[A-Za-z0-9_-]+$/
const SESSION_ID_PATTERN = /^prs_[A-Za-z0-9_-]+$/
const PRESENTATION_STYLES = new Set<PresentationStyle>([
  'modern', 'tech', 'corporate', 'creative', 'minimal', 'dark',
])
const OUTPUT_FORMATS = new Set<PresentationOutputFormat>(['pptx', 'html'])
const ENGINES = new Set<PresentationEngine>([
  'auto', 'ppt_master', 'frontend_slides', 'native_pptx',
])
const MAX_ARTIFACT_SIZE = parseInt(process.env.PRESENTATION_MAX_BYTES || '', 10) || 100 * 1024 * 1024
export const MAX_PRESENTATION_SOURCE_SIZE = parseInt(process.env.PRESENTATION_SOURCE_MAX_BYTES || '', 10) || 100 * 1024 * 1024

function serviceError(message: string, code: string): Error & { code: string } {
  return Object.assign(new Error(message), { code })
}

export function getPresentationsHome(): string {
  return join(resolveReinsHome(), 'presentations')
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

function integerInRange(value: unknown, fallback: number, min: number, max: number, field: string): number {
  const parsed = value == null || value === '' ? fallback : Number(value)
  if (!Number.isInteger(parsed) || parsed < min || parsed > max) {
    throw serviceError(`${field} must be an integer from ${min} to ${max}.`, 'invalid_request')
  }
  return parsed
}

export function normalizePresentationSubmitRequest(body: unknown): PresentationSubmitRequest {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const style = String(input.style || 'modern') as PresentationStyle
  const outputFormat = String(input.output_format || 'pptx') as PresentationOutputFormat
  let engine = String(input.engine || 'auto') as PresentationEngine
  const aspectRatio = String(input.aspect_ratio || '16:9')
  const language = String(input.language || 'zh').trim().slice(0, 20) || 'zh'

  if (!PRESENTATION_STYLES.has(style)) {
    throw serviceError('Invalid presentation style.', 'invalid_request')
  }
  if (!OUTPUT_FORMATS.has(outputFormat)) {
    throw serviceError('Invalid presentation output format.', 'invalid_request')
  }
  if (!ENGINES.has(engine)) {
    throw serviceError('Invalid presentation engine.', 'invalid_request')
  }
  if (aspectRatio !== '16:9' && aspectRatio !== '4:3') {
    throw serviceError('Invalid presentation aspect ratio.', 'invalid_request')
  }

  if (outputFormat === 'html') engine = 'frontend_slides'
  if (outputFormat === 'pptx' && engine === 'frontend_slides') {
    throw serviceError('Frontend Slides only supports HTML output.', 'invalid_request')
  }
  if (outputFormat === 'html' && engine === 'native_pptx') {
    throw serviceError('Native PPTX only supports PowerPoint output.', 'invalid_request')
  }

  return {
    action: 'new',
    prompt: requiredText(input.prompt, 'Presentation brief', 30_000),
    title: optionalText(input.title, 'Title', 180),
    audience: optionalText(input.audience, 'Audience', 300),
    language,
    slide_count: integerInRange(input.slide_count, 8, 3, 30, 'Slide count'),
    style,
    output_format: outputFormat,
    engine,
    aspect_ratio: aspectRatio,
    run_qa: input.run_qa !== false,
    maximum_qa_rounds: 1,
    metadata: { origin: 'reins-web' },
  }
}

export function normalizePresentationChatCreateRequest(body: unknown): PresentationSubmitRequest {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const requestedEngine = String(input.engine || 'auto')
  return normalizePresentationSubmitRequest({
    ...input,
    output_format: 'pptx',
    engine: requestedEngine === 'frontend_slides' ? 'auto' : requestedEngine,
  })
}

export function normalizePresentationSessionTurnRequest(body: unknown): Omit<PresentationSubmitRequest, 'source_path'> {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const action = String(input.action || 'modify') as PresentationAction
  const style = String(input.style || 'modern') as PresentationStyle
  const language = String(input.language || 'zh').trim().slice(0, 20) || 'zh'
  const outputFormat = String(input.output_format || (action === 'convert' ? 'html' : 'pptx')) as PresentationOutputFormat

  if (!['modify', 'restyle', 'convert'].includes(action)) {
    throw serviceError('Invalid presentation operation.', 'invalid_request')
  }
  if (!PRESENTATION_STYLES.has(style)) {
    throw serviceError('Invalid presentation style.', 'invalid_request')
  }
  if (action === 'convert' && !['html', 'pdf'].includes(outputFormat)) {
    throw serviceError('Conversion output must be HTML or PDF.', 'invalid_request')
  }
  if (action !== 'convert' && outputFormat !== 'pptx') {
    throw serviceError('Modify and restyle operations produce PPTX revisions.', 'invalid_request')
  }

  return {
    action: action as Exclude<PresentationAction, 'new'>,
    instruction: requiredText(input.instruction, 'Instruction', 10_000),
    language,
    slide_count: 8,
    style,
    output_format: outputFormat,
    engine: action === 'convert' && outputFormat === 'html' ? 'frontend_slides' : 'auto',
    aspect_ratio: '16:9',
    run_qa: input.run_qa !== false,
    maximum_qa_rounds: 1,
    metadata: { origin: 'reins-web-editor' },
  }
}

export function validatePresentationJobId(jobId: unknown): string {
  const value = String(jobId || '').trim()
  if (!JOB_ID_PATTERN.test(value)) {
    throw serviceError('Invalid presentation job id.', 'invalid_request')
  }
  return value
}

export function validatePresentationSessionId(sessionId: unknown): string {
  const value = String(sessionId || '').trim()
  if (!SESSION_ID_PATTERN.test(value)) {
    throw serviceError('Invalid presentation session id.', 'invalid_request')
  }
  return value
}

function resolveReinsBin(): string {
  return process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim() || 'reins'
}

async function runSubmitCommand(request: PresentationSubmitRequest): Promise<Record<string, unknown>> {
  const child = spawn(resolveReinsBin(), ['presentation', 'submit'], {
    env: { ...process.env },
    windowsHide: true,
    stdio: ['pipe', 'pipe', 'pipe'],
  })
  let stdout = ''
  let stderr = ''
  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')
  child.stdout.on('data', chunk => { stdout += chunk })
  child.stderr.on('data', chunk => { stderr += chunk })
  child.stdin.end(JSON.stringify(request))

  const timeout = setTimeout(() => child.kill(), 15_000)
  try {
    const closePromise = once(child, 'close') as Promise<[number | null, NodeJS.Signals | null]>
    const errorPromise = once(child, 'error').then(([error]) => { throw error as Error })
    const [code] = await Promise.race([closePromise, errorPromise])
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(stdout) as Record<string, unknown>
    } catch {
      throw serviceError(stderr.trim() || 'Presentation worker returned invalid output.', 'worker_error')
    }
    if (code !== 0 || typeof payload.job_id !== 'string') {
      throw serviceError(String(payload.error || stderr.trim() || 'Presentation job could not be submitted.'), 'worker_error')
    }
    return payload
  } finally {
    clearTimeout(timeout)
  }
}

async function readJson(path: string): Promise<Record<string, unknown>> {
  try {
    const value = JSON.parse(await readFile(path, 'utf8'))
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('not an object')
    return value as Record<string, unknown>
  } catch (error: any) {
    if (error?.code === 'ENOENT') throw serviceError('Presentation job not found.', 'not_found')
    throw serviceError('Presentation job data is invalid.', 'invalid_state')
  }
}

function safeBasename(value: unknown): string | null {
  if (typeof value !== 'string' || !value.trim()) return null
  return basename(value)
}

function toJobDto(state: Record<string, unknown>): PresentationJobDto {
  const outputFileName = safeBasename(state.output_path)
  const rawArtifacts = Array.isArray(state.artifacts) ? state.artifacts : []
  const artifacts = rawArtifacts.flatMap((value): PresentationArtifactDto[] => {
    if (!value || typeof value !== 'object') return []
    const artifact = value as Record<string, unknown>
    const fileName = safeBasename(artifact.path)
    if (!fileName) return []
    return [{
      kind: String(artifact.kind || 'artifact'),
      file_name: fileName,
      mime_type: typeof artifact.mime_type === 'string' ? artifact.mime_type : null,
    }]
  })

  return {
    job_id: String(state.job_id || ''),
    status: String(state.status || 'created'),
    progress: Number(state.progress || 0),
    phase: String(state.phase || ''),
    action: String(state.action || 'new'),
    engine: String(state.engine || 'auto'),
    created_at: String(state.created_at || ''),
    updated_at: String(state.updated_at || ''),
    error: typeof state.error === 'string' && state.error ? state.error : null,
    warnings: Array.isArray(state.warnings) ? state.warnings.map(String) : [],
    artifacts,
    metadata: state.metadata && typeof state.metadata === 'object' && !Array.isArray(state.metadata)
      ? state.metadata as Record<string, unknown>
      : {},
    has_output: Boolean(outputFileName && state.status === 'completed'),
    output_file_name: outputFileName,
    preview_available: Boolean(
      outputFileName
      && ['.html', '.pdf'].includes(extname(outputFileName).toLowerCase())
      && state.status === 'completed',
    ),
  }
}

export async function submitPresentationJob(body: unknown): Promise<PresentationJobDto> {
  const request = normalizePresentationSubmitRequest(body)
  const state = await runSubmitCommand(request)
  return toJobDto(state)
}

export async function getPresentationJob(jobId: unknown): Promise<PresentationJobDto> {
  const safeId = validatePresentationJobId(jobId)
  const state = await readJson(join(getPresentationsHome(), safeId, 'status.json'))
  return toJobDto(state)
}

export async function listPresentationJobs(limitValue: unknown = 20): Promise<PresentationJobDto[]> {
  const limit = integerInRange(limitValue, 20, 1, 100, 'Limit')
  let entries
  try {
    entries = await readdir(getPresentationsHome(), { withFileTypes: true })
  } catch (error: any) {
    if (error?.code === 'ENOENT') return []
    throw error
  }

  const ids = entries
    .filter(entry => entry.isDirectory() && JOB_ID_PATTERN.test(entry.name))
    .map(entry => entry.name)
    .sort()
    .reverse()
    .slice(0, limit)

  const states = await Promise.all(ids.map(async id => {
    try {
      return await getPresentationJob(id)
    } catch {
      return null
    }
  }))
  return states.filter((state): state is PresentationJobDto => state !== null)
}

function isPathInside(path: string, root: string): boolean {
  const rel = relative(root, path)
  return rel === '' || (!!rel && !rel.startsWith('..') && !isAbsolute(rel))
}

export async function getPresentationMedia(jobId: unknown, preview = false): Promise<PresentationMedia> {
  const safeId = validatePresentationJobId(jobId)
  const jobRoot = join(getPresentationsHome(), safeId)
  const state = await readJson(join(jobRoot, 'status.json'))
  if (state.status !== 'completed' || typeof state.output_path !== 'string') {
    throw serviceError('Presentation output is not ready.', 'not_ready')
  }

  const extension = extname(state.output_path).toLowerCase()
  if (!['.pptx', '.html', '.pdf'].includes(extension)) {
    throw serviceError('Presentation output type is not allowed.', 'invalid_state')
  }
  if (preview && !['.html', '.pdf'].includes(extension)) {
    throw serviceError('Only HTML and PDF presentations can be previewed.', 'invalid_request')
  }

  let resolvedRoot: string
  let resolvedOutput: string
  try {
    [resolvedRoot, resolvedOutput] = await Promise.all([
      realpath(jobRoot),
      realpath(state.output_path),
    ])
  } catch {
    throw serviceError('Presentation output was not found.', 'not_found')
  }
  if (!isPathInside(resolvedOutput, resolvedRoot)) {
    throw serviceError('Presentation output is outside its job workspace.', 'invalid_state')
  }

  const fileStat = await stat(resolvedOutput)
  if (!fileStat.isFile()) throw serviceError('Presentation output was not found.', 'not_found')
  if (fileStat.size > MAX_ARTIFACT_SIZE) {
    throw serviceError('Presentation output is too large to serve.', 'file_too_large')
  }

  return {
    stream: createReadStream(resolvedOutput),
    fileName: basename(resolvedOutput),
    mime: extension === '.html'
      ? 'text/html; charset=utf-8'
      : extension === '.pdf'
        ? 'application/pdf'
        : 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    size: fileStat.size,
  }
}

function sessionRoot(sessionId: string): string {
  return join(getPresentationsHome(), 'sessions', sessionId)
}

function sessionStatePath(sessionId: string): string {
  return join(sessionRoot(sessionId), 'session.json')
}

function createSessionId(): string {
  const timestamp = new Date().toISOString().replace(/\D/g, '').slice(0, 14)
  return `prs_${timestamp}_${randomBytes(4).toString('hex')}`
}

function isoNow(): string {
  return new Date().toISOString()
}

async function writeSession(session: StoredPresentationSession): Promise<void> {
  const statePath = sessionStatePath(session.session_id)
  const temporaryPath = `${statePath}.tmp`
  await writeFile(temporaryPath, JSON.stringify(session, null, 2), { encoding: 'utf8', mode: 0o600 })
  await rename(temporaryPath, statePath)
}

async function readSession(sessionId: unknown): Promise<StoredPresentationSession> {
  const safeId = validatePresentationSessionId(sessionId)
  const value = await readJson(sessionStatePath(safeId))
  if (value.schema !== 'reins_presentation_session.v1' || !Array.isArray(value.turns)) {
    throw serviceError('Presentation session data is invalid.', 'invalid_state')
  }
  const session = value as unknown as StoredPresentationSession
  if (!session.source_type) {
    const extension = extname(session.source_path || '').toLowerCase()
    session.source_type = extension === '.pdf' ? 'pdf' : extension === '.pptx' ? 'pptx' : 'prompt'
  }
  if (session.source_path === undefined) session.source_path = null
  return session
}

function isTerminalStatus(status: string): boolean {
  return status === 'completed' || status === 'failed'
}

async function readJobState(jobId: string): Promise<Record<string, unknown>> {
  return readJson(join(getPresentationsHome(), validatePresentationJobId(jobId), 'status.json'))
}

async function refreshSession(session: StoredPresentationSession): Promise<StoredPresentationSession> {
  let activeRevision = session.active_revision
  for (const turn of session.turns) {
    if (!turn.advances_deck || turn.parent_revision !== activeRevision) continue
    const state = await readJobState(turn.job_id)
    if (state.status === 'completed' && typeof state.output_path === 'string') {
      activeRevision = turn.turn
    }
  }
  if (activeRevision === session.active_revision) return session
  const refreshed = { ...session, active_revision: activeRevision, updated_at: isoNow() }
  await writeSession(refreshed)
  return refreshed
}

async function sessionSourcePath(session: StoredPresentationSession): Promise<string> {
  if (session.active_revision === 0) {
    if (!session.source_path) {
      throw serviceError('This presentation does not have a source file.', 'invalid_state')
    }
    return realpath(session.source_path)
  }
  const turn = session.turns.find(value => value.turn === session.active_revision)
  if (!turn) throw serviceError('Active presentation revision is missing.', 'invalid_state')
  const state = await readJobState(turn.job_id)
  if (state.status !== 'completed' || typeof state.output_path !== 'string') {
    throw serviceError('Active presentation revision is not ready.', 'invalid_state')
  }
  const jobRoot = await realpath(join(getPresentationsHome(), turn.job_id))
  const output = await realpath(state.output_path)
  if (!isPathInside(output, jobRoot) || extname(output).toLowerCase() !== '.pptx') {
    throw serviceError('Active presentation revision is invalid.', 'invalid_state')
  }
  return output
}

async function toSessionDto(sessionValue: StoredPresentationSession): Promise<PresentationSessionDto> {
  const session = await refreshSession(sessionValue)
  const turns = await Promise.all(session.turns.map(async turn => ({
    ...turn,
    job: toJobDto(await readJobState(turn.job_id)),
  })))
  return {
    session_id: session.session_id,
    name: session.name,
    source_file_name: session.source_file_name,
    source_type: session.source_type,
    deck_ready: session.active_revision > 0 || session.source_type === 'pptx',
    active_revision: session.active_revision,
    created_at: session.created_at,
    updated_at: session.updated_at,
    turns,
  }
}

export async function createPresentationSession(
  fileNameValue: unknown,
  data: Buffer,
): Promise<PresentationSessionDto> {
  const sourceFileName = basename(requiredText(fileNameValue, 'File name', 255))
  const extension = extname(sourceFileName).toLowerCase()
  if (extension !== '.pptx' && extension !== '.pdf') {
    throw serviceError('Presentation sessions require a PPTX or PDF file.', 'invalid_request')
  }
  if (!data.length) throw serviceError('The uploaded presentation source is empty.', 'invalid_request')
  if (data.length > MAX_PRESENTATION_SOURCE_SIZE) {
    throw serviceError('The uploaded presentation source is too large.', 'file_too_large')
  }
  if (extension === '.pptx' && (data[0] !== 0x50 || data[1] !== 0x4b)) {
    throw serviceError('The uploaded file is not a valid PPTX package.', 'invalid_request')
  }
  if (extension === '.pdf' && !data.subarray(0, 1024).includes(Buffer.from('%PDF-'))) {
    throw serviceError('The uploaded file is not a valid PDF document.', 'invalid_request')
  }

  const sessionId = createSessionId()
  const root = sessionRoot(sessionId)
  await mkdir(join(getPresentationsHome(), 'sessions'), { recursive: true, mode: 0o700 })
  await mkdir(root, { recursive: false, mode: 0o700 })
  const sourcePath = join(root, `source${extension}`)
  await writeFile(sourcePath, data, { mode: 0o600 })
  const now = isoNow()
  const session: StoredPresentationSession = {
    schema: 'reins_presentation_session.v1',
    session_id: sessionId,
    name: sourceFileName.replace(/\.(pptx|pdf)$/i, ''),
    source_file_name: sourceFileName,
    source_path: sourcePath,
    source_type: extension.slice(1) as PresentationSessionSourceType,
    active_revision: 0,
    created_at: now,
    updated_at: now,
    turns: [],
  }
  await writeSession(session)
  return toSessionDto(session)
}

function presentationName(request: PresentationSubmitRequest): string {
  if (request.title) return request.title
  const firstLine = String(request.prompt || '').split(/\r?\n/, 1)[0]?.trim() || 'New presentation'
  return firstLine.length > 72 ? `${firstLine.slice(0, 69).trimEnd()}...` : firstLine
}

export async function createPresentationChat(body: unknown): Promise<PresentationSessionDto> {
  const normalized = normalizePresentationChatCreateRequest(body)
  const sessionId = createSessionId()
  const root = sessionRoot(sessionId)
  await mkdir(join(getPresentationsHome(), 'sessions'), { recursive: true, mode: 0o700 })
  await mkdir(root, { recursive: false, mode: 0o700 })
  const now = isoNow()
  let session: StoredPresentationSession = {
    schema: 'reins_presentation_session.v1',
    session_id: sessionId,
    name: presentationName(normalized),
    source_file_name: '',
    source_path: null,
    source_type: 'prompt',
    active_revision: 0,
    created_at: now,
    updated_at: now,
    turns: [],
  }
  await writeSession(session)

  try {
    const state = await runSubmitCommand({
      ...normalized,
      metadata: {
        ...normalized.metadata,
        session_id: session.session_id,
        parent_revision: 0,
      },
    })
    const turn: StoredPresentationTurn = {
      turn: 1,
      action: 'new',
      instruction: String(normalized.prompt),
      style: normalized.style,
      output_format: 'pptx',
      job_id: validatePresentationJobId(state.job_id),
      parent_revision: 0,
      advances_deck: true,
      created_at: isoNow(),
    }
    session = { ...session, updated_at: isoNow(), turns: [turn] }
    await writeSession(session)
    return toSessionDto(session)
  } catch (error) {
    await rm(root, { recursive: true, force: true })
    throw error
  }
}

export async function getPresentationSession(sessionId: unknown): Promise<PresentationSessionDto> {
  return toSessionDto(await readSession(sessionId))
}

export async function listPresentationSessions(limitValue: unknown = 20): Promise<PresentationSessionDto[]> {
  const limit = integerInRange(limitValue, 20, 1, 100, 'Limit')
  const root = join(getPresentationsHome(), 'sessions')
  let entries
  try {
    entries = await readdir(root, { withFileTypes: true })
  } catch (error: any) {
    if (error?.code === 'ENOENT') return []
    throw error
  }
  const ids = entries
    .filter(entry => entry.isDirectory() && SESSION_ID_PATTERN.test(entry.name))
    .map(entry => entry.name)
    .sort()
    .reverse()
    .slice(0, limit)
  const sessions = await Promise.all(ids.map(async id => {
    try { return await getPresentationSession(id) } catch { return null }
  }))
  return sessions.filter((session): session is PresentationSessionDto => session !== null)
}

const sessionMutations = new Map<string, Promise<unknown>>()

async function serializeSessionMutation<T>(sessionId: string, operation: () => Promise<T>): Promise<T> {
  const previous = sessionMutations.get(sessionId) || Promise.resolve()
  const current = previous.catch(() => undefined).then(operation)
  sessionMutations.set(sessionId, current)
  try {
    return await current
  } finally {
    if (sessionMutations.get(sessionId) === current) sessionMutations.delete(sessionId)
  }
}

async function submitPresentationSessionTurnUnlocked(
  sessionId: string,
  body: unknown,
): Promise<PresentationSessionDto> {
  let session = await refreshSession(await readSession(sessionId))
  const activeStates = await Promise.all(session.turns.map(turn => readJobState(turn.job_id)))
  if (activeStates.some(state => !isTerminalStatus(String(state.status || '')))) {
    throw serviceError('Wait for the current presentation operation to finish.', 'conflict')
  }

  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const needsInitialDeck = session.active_revision === 0 && session.source_type !== 'pptx'
  let request: PresentationSubmitRequest
  let instruction: string

  if (needsInitialDeck) {
    const normalized = normalizePresentationChatCreateRequest({
      ...input,
      prompt: input.instruction ?? input.prompt,
    })
    request = {
      ...normalized,
      source_path: session.source_path ? await sessionSourcePath(session) : undefined,
      metadata: {
        ...normalized.metadata,
        session_id: session.session_id,
        parent_revision: session.active_revision,
      },
    }
    instruction = String(normalized.prompt)
  } else {
    const normalized = normalizePresentationSessionTurnRequest(body)
    request = {
      ...normalized,
      source_path: await sessionSourcePath(session),
      metadata: {
        ...normalized.metadata,
        session_id: session.session_id,
        parent_revision: session.active_revision,
      },
    }
    instruction = String(normalized.instruction)
  }

  const state = await runSubmitCommand(request)
  const jobId = validatePresentationJobId(state.job_id)
  const action = request.action
  const turn: StoredPresentationTurn = {
    turn: Math.max(0, ...session.turns.map(value => value.turn)) + 1,
    action,
    instruction,
    style: request.style,
    output_format: request.output_format,
    job_id: jobId,
    parent_revision: session.active_revision,
    advances_deck: action === 'new' || action === 'modify' || action === 'restyle',
    created_at: isoNow(),
  }
  session = {
    ...session,
    updated_at: isoNow(),
    turns: [...session.turns, turn],
  }
  await writeSession(session)
  return toSessionDto(session)
}

export async function submitPresentationSessionTurn(
  sessionId: unknown,
  body: unknown,
): Promise<PresentationSessionDto> {
  const safeId = validatePresentationSessionId(sessionId)
  return serializeSessionMutation(
    safeId,
    () => submitPresentationSessionTurnUnlocked(safeId, body),
  )
}
