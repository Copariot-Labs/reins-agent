import { spawn, type ChildProcessWithoutNullStreams } from 'child_process'
import { once } from 'events'
import { PassThrough } from 'stream'
import { logger } from '../logger'

export type WorkModeName = 'work' | 'demo' | 'headless'

export interface WorkModeRunRequest {
  message: string
  mode: WorkModeName
}

export interface WorkModeEvent {
  type: string
  message: string
  task_id?: string | null
  data: Record<string, unknown>
  created_at: string
}

export interface WorkModeStream {
  stream: PassThrough
  cancel: () => void
}

export interface WorkModeCaseSummary {
  case_id: string
  message?: string | null
  issue_type?: string | null
  priority?: string | null
  location?: string | null
  workflow?: string | null
  status?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface WorkModeCaseReplay {
  ok: boolean
  error?: string
  case_id?: string
  case?: WorkModeCaseSummary | null
  events?: Record<string, unknown>[]
  artifacts?: Record<string, unknown>[]
}

export interface WorkModeConfirmationResult {
  ok: boolean
  error?: string
  case_id?: string
  confirmation_id?: string
  status?: string
  result?: Record<string, unknown>
}

const WORKMODE_MODES = new Set<WorkModeName>(['work', 'demo', 'headless'])

function nowIso(): string {
  return new Date().toISOString()
}

function resolveReinsBin(): string {
  return process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim() || 'reins'
}

function event(type: string, message: string, data: Record<string, unknown> = {}): WorkModeEvent {
  return {
    type,
    message,
    data,
    created_at: nowIso(),
  }
}

function writeSse(stream: PassThrough, payload: WorkModeEvent): void {
  stream.write(`data: ${JSON.stringify(payload)}\n\n`)
}

function normalizeMode(value: unknown): WorkModeName {
  const mode = String(value || 'work').trim()
  if (WORKMODE_MODES.has(mode as WorkModeName)) return mode as WorkModeName
  throw new Error(`Invalid workmode mode: ${mode || '(empty)'}`)
}

export function normalizeWorkModeRunRequest(body: unknown): WorkModeRunRequest {
  const input = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const message = String(input.message || input.input || '').trim()

  if (!message) {
    throw new Error('Work mode message is required')
  }

  return {
    message,
    mode: normalizeMode(input.mode),
  }
}

function parseCliEvent(line: string): WorkModeEvent {
  const trimmed = line.trim()
  if (!trimmed) return event('work.stream.empty', '')

  try {
    const parsed = JSON.parse(trimmed) as Partial<WorkModeEvent>
    if (typeof parsed.type === 'string' && typeof parsed.message === 'string') {
      return {
        type: parsed.type,
        message: parsed.message,
        task_id: parsed.task_id ?? null,
        data: parsed.data && typeof parsed.data === 'object'
          ? parsed.data as Record<string, unknown>
          : {},
        created_at: typeof parsed.created_at === 'string' ? parsed.created_at : nowIso(),
      }
    }
  } catch {
    // Fall through to a visible stream line.
  }

  return event('work.stream.output', trimmed, { line: trimmed })
}

function drainLines(buffer: string, onLine: (line: string) => void, flush = false): string {
  const lines = buffer.split(/\r?\n/)
  const remainder = lines.pop() || ''

  for (const line of lines) {
    if (line.trim()) onLine(line)
  }

  if (flush && remainder.trim()) {
    onLine(remainder)
    return ''
  }

  return remainder
}

function killChild(child: ChildProcessWithoutNullStreams): void {
  if (child.killed) return
  try {
    child.kill()
  } catch (err) {
    logger.warn(err, 'Failed to cancel Reins workmode process')
  }
}

async function runJsonCommand<T = Record<string, unknown>>(args: string[]): Promise<T> {
  const bin = resolveReinsBin()
  const child = spawn(bin, args, {
    env: { ...process.env },
    windowsHide: true,
  })

  let stdout = ''
  let stderr = ''

  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')
  child.stdout.on('data', (chunk: string) => {
    stdout += chunk
  })
  child.stderr.on('data', (chunk: string) => {
    stderr += chunk
  })

  const closePromise = once(child, 'close') as Promise<[number | null, NodeJS.Signals | null]>
  const errorPromise = once(child, 'error').then(([err]) => {
    throw err as Error
  })
  const [code, signal] = await Promise.race([closePromise, errorPromise])

  try {
    const payload = JSON.parse(stdout) as T
    if (code !== 0 && (!payload || typeof payload !== 'object')) {
      throw new Error(stderr.trim() || `Reins workmode command failed with code ${code ?? signal ?? 'unknown'}`)
    }
    return payload
  } catch (err: any) {
    if (code !== 0) {
      throw new Error(stderr.trim() || `Reins workmode command failed with code ${code ?? signal ?? 'unknown'}`)
    }
    throw new Error(`Failed to parse Reins workmode JSON output: ${err?.message || err}`)
  }
}

export async function listWorkModeCases(limit = 25): Promise<{ ok: boolean, cases: WorkModeCaseSummary[] }> {
  const safeLimit = Math.max(1, Math.min(Math.trunc(limit) || 25, 100))
  const payload = await runJsonCommand<{ ok?: boolean, cases?: unknown }>(['workmode', 'cases', '--limit', String(safeLimit)])
  const cases = Array.isArray(payload.cases) ? payload.cases as WorkModeCaseSummary[] : []
  return {
    ok: payload.ok !== false,
    cases,
  }
}

export async function getWorkModeCase(caseId: string): Promise<WorkModeCaseReplay> {
  const cleanCaseId = String(caseId || '').trim()
  if (!cleanCaseId) throw new Error('Work mode case id is required')
  return await runJsonCommand<WorkModeCaseReplay>(['workmode', 'replay', cleanCaseId])
}

export async function approveWorkModeConfirmation(caseId: string, confirmationId: string): Promise<WorkModeConfirmationResult> {
  const cleanCaseId = String(caseId || '').trim()
  const cleanConfirmationId = String(confirmationId || '').trim()
  if (!cleanCaseId) throw new Error('Work mode case id is required')
  if (!cleanConfirmationId) throw new Error('Work mode confirmation id is required')
  return await runJsonCommand<WorkModeConfirmationResult>(['workmode', 'approve', cleanCaseId, cleanConfirmationId])
}

export async function rejectWorkModeConfirmation(caseId: string, confirmationId: string, reason = ''): Promise<WorkModeConfirmationResult> {
  const cleanCaseId = String(caseId || '').trim()
  const cleanConfirmationId = String(confirmationId || '').trim()
  if (!cleanCaseId) throw new Error('Work mode case id is required')
  if (!cleanConfirmationId) throw new Error('Work mode confirmation id is required')
  const args = ['workmode', 'reject', cleanCaseId, cleanConfirmationId]
  if (reason.trim()) args.push('--reason', reason.trim())
  return await runJsonCommand<WorkModeConfirmationResult>(args)
}

export function startWorkModeRun(input: WorkModeRunRequest): WorkModeStream {
  const stream = new PassThrough()
  const bin = resolveReinsBin()
  const args = ['workmode', 'run', input.message, '--mode', input.mode]
  const child = spawn(bin, args, {
    env: { ...process.env },
    windowsHide: true,
  })

  let stdoutBuffer = ''
  let stderrBuffer = ''
  let childClosed = false
  let sawTerminalEvent = false

  const emit = (payload: WorkModeEvent) => {
    if (payload.type === 'task_finished' || payload.type === 'task_failed') {
      sawTerminalEvent = true
    }
    writeSse(stream, payload)
  }

  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')

  child.stdout.on('data', (chunk: string) => {
    stdoutBuffer += chunk
    stdoutBuffer = drainLines(stdoutBuffer, (line) => emit(parseCliEvent(line)))
  })

  child.stderr.on('data', (chunk: string) => {
    stderrBuffer += chunk
    stderrBuffer = drainLines(stderrBuffer, (line) => {
      emit(event('work.stream.stderr', line.trim(), { stream: 'stderr' }))
    })
  })

  child.on('error', (err) => {
    childClosed = true
    logger.error(err, 'Failed to start Reins workmode process')
    emit(event('task_failed', `Work mode process failed to start: ${err.message}`, {
      error_type: err.name,
      error: err.message,
      command: bin,
    }))
    stream.end()
  })

  child.on('close', (code, signal) => {
    childClosed = true
    stdoutBuffer = drainLines(stdoutBuffer, (line) => emit(parseCliEvent(line)), true)
    stderrBuffer = drainLines(stderrBuffer, (line) => {
      emit(event('work.stream.stderr', line.trim(), { stream: 'stderr' }))
    }, true)

    if (!sawTerminalEvent && code !== 0) {
      emit(event('task_failed', 'Work mode process exited before completing.', {
        exit_code: code,
        signal,
        command: bin,
      }))
    }

    stream.end()
  })

  stream.on('close', () => {
    if (!childClosed) killChild(child)
  })

  return {
    stream,
    cancel: () => {
      if (!childClosed) killChild(child)
    },
  }
}
