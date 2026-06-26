import { getActiveProfileName, getApiKey, getBaseUrlValue } from '../client'

export type WorkModeName = 'work' | 'demo' | 'headless'

export interface WorkModeEvent {
  type: string
  message: string
  task_id?: string | null
  data: Record<string, any>
  created_at: string
}

export interface WorkModeRunInput {
  message: string
  mode?: WorkModeName
}

export interface WorkModeStreamOptions {
  signal?: AbortSignal
  onEvent: (event: WorkModeEvent) => void
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
  events?: WorkModeEvent[]
  artifacts?: Record<string, any>[]
}

export interface WorkModeConfirmationResult {
  ok: boolean
  error?: string
  case_id?: string
  confirmation_id?: string
  status?: string
  result?: Record<string, any>
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }

  const apiKey = getApiKey()
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`

  const profileName = getActiveProfileName()
  if (profileName) headers['X-Hermes-Profile'] = profileName

  return headers
}

function dispatchSseBlock(block: string, onEvent: (event: WorkModeEvent) => void): void {
  const data = block
    .split('\n')
    .filter(line => line.startsWith('data:'))
    .map(line => line.replace(/^data:\s?/, ''))
    .join('\n')
    .trim()

  if (!data) return
  onEvent(JSON.parse(data) as WorkModeEvent)
}

function consumeSseBuffer(buffer: string, onEvent: (event: WorkModeEvent) => void, flush = false): string {
  let normalized = buffer.replace(/\r\n/g, '\n')
  let index = normalized.indexOf('\n\n')

  while (index >= 0) {
    const block = normalized.slice(0, index)
    normalized = normalized.slice(index + 2)
    dispatchSseBlock(block, onEvent)
    index = normalized.indexOf('\n\n')
  }

  if (flush && normalized.trim()) {
    dispatchSseBlock(normalized, onEvent)
    return ''
  }

  return normalized
}

export async function runWorkModeStream(
  input: WorkModeRunInput,
  options: WorkModeStreamOptions,
): Promise<void> {
  const response = await fetch(`${getBaseUrlValue()}/api/hermes/workmode/run`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(input),
    signal: options.signal,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`API Error ${response.status}: ${text || response.statusText}`)
  }

  if (!response.body) {
    throw new Error('Work mode stream is not available in this browser')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = consumeSseBuffer(buffer, options.onEvent)
  }

  buffer += decoder.decode()
  consumeSseBuffer(buffer, options.onEvent, true)
}

async function jsonRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${getBaseUrlValue()}${path}`, {
    ...init,
    headers: authHeaders(),
    body: init.body,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`API Error ${response.status}: ${text || response.statusText}`)
  }

  return await response.json() as T
}

export async function listWorkModeCases(limit = 25): Promise<WorkModeCaseSummary[]> {
  const payload = await jsonRequest<{ ok: boolean, cases: WorkModeCaseSummary[] }>(
    `/api/hermes/workmode/cases?limit=${encodeURIComponent(String(limit))}`,
  )
  return Array.isArray(payload.cases) ? payload.cases : []
}

export async function getWorkModeCase(caseId: string): Promise<WorkModeCaseReplay> {
  return await jsonRequest<WorkModeCaseReplay>(
    `/api/hermes/workmode/cases/${encodeURIComponent(caseId)}`,
  )
}

export async function approveWorkModeConfirmation(caseId: string, confirmationId: string): Promise<WorkModeConfirmationResult> {
  return await jsonRequest<WorkModeConfirmationResult>(
    `/api/hermes/workmode/cases/${encodeURIComponent(caseId)}/confirmations/${encodeURIComponent(confirmationId)}/approve`,
    { method: 'POST' },
  )
}

export async function rejectWorkModeConfirmation(caseId: string, confirmationId: string, reason = ''): Promise<WorkModeConfirmationResult> {
  return await jsonRequest<WorkModeConfirmationResult>(
    `/api/hermes/workmode/cases/${encodeURIComponent(caseId)}/confirmations/${encodeURIComponent(confirmationId)}/reject`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
    },
  )
}
