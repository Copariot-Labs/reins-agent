import { getActiveProfileName, getApiKey, getBaseUrlValue, request } from '../client'

export type PresentationStyle = 'modern' | 'tech' | 'corporate' | 'creative' | 'minimal' | 'dark'
export type PresentationOutputFormat = 'pptx' | 'html'
export type PresentationAction = 'new' | 'modify' | 'restyle' | 'convert'
export type PresentationEditOutputFormat = 'pptx' | 'html' | 'pdf'

export interface PresentationSubmitInput {
  prompt: string
  title?: string
  audience?: string
  language?: string
  slide_count: number
  style: PresentationStyle
  output_format: PresentationOutputFormat
  engine?: 'auto' | 'ppt_master' | 'frontend_slides' | 'native_pptx'
  aspect_ratio?: '16:9' | '4:3'
  run_qa?: boolean
}

export interface PresentationArtifact {
  kind: string
  file_name: string
  mime_type: string | null
}

export interface PresentationJob {
  job_id: string
  status: 'created' | 'planning' | 'plan_ready' | 'rendering' | 'qa' | 'completed' | 'failed' | string
  progress: number
  phase: string
  action: string
  engine: string
  created_at: string
  updated_at: string
  error: string | null
  warnings: string[]
  artifacts: PresentationArtifact[]
  metadata: Record<string, unknown>
  has_output: boolean
  output_file_name: string | null
  preview_available: boolean
}

export interface PresentationSessionTurn {
  turn: number
  action: PresentationAction
  instruction: string
  style: PresentationStyle
  output_format: PresentationEditOutputFormat
  parent_revision: number
  advances_deck: boolean
  created_at: string
  job: PresentationJob
}

export interface PresentationSession {
  session_id: string
  name: string
  source_file_name: string
  source_type: 'prompt' | 'pptx' | 'pdf'
  deck_ready: boolean
  active_revision: number
  created_at: string
  updated_at: string
  turns: PresentationSessionTurn[]
}

export interface PresentationSessionMessageInput {
  action: PresentationAction
  instruction: string
  style: PresentationStyle
  output_format: PresentationEditOutputFormat
  title?: string
  audience?: string
  slide_count?: number
  aspect_ratio?: '16:9' | '4:3'
  language?: string
  run_qa?: boolean
}

export type PresentationChatCreateInput = Omit<PresentationSubmitInput, 'output_format'>

export async function submitPresentation(input: PresentationSubmitInput): Promise<PresentationJob> {
  const response = await request<{ job: PresentationJob }>('/api/hermes/presentations', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return response.job
}

export async function fetchPresentationJob(jobId: string): Promise<PresentationJob> {
  const response = await request<{ job: PresentationJob }>(`/api/hermes/presentations/${encodeURIComponent(jobId)}`)
  return response.job
}

export async function fetchPresentationJobs(limit = 20): Promise<PresentationJob[]> {
  const response = await request<{ jobs: PresentationJob[] }>(`/api/hermes/presentations?limit=${limit}`)
  return response.jobs
}

export async function createPresentationSession(file: File): Promise<PresentationSession> {
  const body = new FormData()
  body.append('file', file, file.name)
  const response = await request<{ session: PresentationSession }>(
    '/api/hermes/presentation-sessions',
    { method: 'POST', body },
  )
  return response.session
}

export async function createPresentationChat(input: PresentationChatCreateInput): Promise<PresentationSession> {
  const response = await request<{ session: PresentationSession }>(
    '/api/hermes/presentation-sessions/create',
    { method: 'POST', body: JSON.stringify(input) },
  )
  return response.session
}

export async function fetchPresentationSession(sessionId: string): Promise<PresentationSession> {
  const response = await request<{ session: PresentationSession }>(
    `/api/hermes/presentation-sessions/${encodeURIComponent(sessionId)}`,
  )
  return response.session
}

export async function fetchPresentationSessions(limit = 20): Promise<PresentationSession[]> {
  const response = await request<{ sessions: PresentationSession[] }>(
    `/api/hermes/presentation-sessions?limit=${limit}`,
  )
  return response.sessions
}

export async function sendPresentationSessionMessage(
  sessionId: string,
  input: PresentationSessionMessageInput,
): Promise<PresentationSession> {
  const response = await request<{ session: PresentationSession }>(
    `/api/hermes/presentation-sessions/${encodeURIComponent(sessionId)}/messages`,
    { method: 'POST', body: JSON.stringify(input) },
  )
  return response.session
}

function authenticatedUrl(path: string): string {
  const apiKey = getApiKey()
  const base = getBaseUrlValue() || window.location.origin
  const url = new URL(path, base)
  if (apiKey) url.searchParams.set('token', apiKey)
  const profile = getActiveProfileName()
  if (profile) url.searchParams.set('profile', profile)
  return url.toString()
}

export function presentationDownloadUrl(jobId: string): string {
  return authenticatedUrl(`/api/hermes/presentations/${encodeURIComponent(jobId)}/download`)
}

export function presentationPreviewUrl(jobId: string): string {
  return authenticatedUrl(`/api/hermes/presentations/${encodeURIComponent(jobId)}/preview`)
}
