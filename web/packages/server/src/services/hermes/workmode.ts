import { spawn, type ChildProcessWithoutNullStreams } from 'child_process'
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
