import { getActiveProfileName, getApiKey, getBaseUrlValue, request } from '../client'

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

export interface OfficeDocument {
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

export interface OfficeSkill {
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

export interface OfficeCreateInput {
  format: OfficeFormat
  prompt: string
  title?: string
  language?: string
  skill_id?: string
  presentation?: OfficePresentationOptions
}

export interface OfficeStatus {
  available: boolean
  error: string | null
  setup_hint: string
  reins_available: boolean
  documents: number
}

export type OfficeOperationStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface OfficeProgressEvent {
  stage: string
  percent: number
  message_zh: string
  message_en: string
  at: string
}

export interface OfficeOperationError {
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

export interface OfficeOperation {
  id: string
  kind: 'create' | 'revise'
  status: OfficeOperationStatus
  percent: number
  created_at: string
  updated_at: string
  events: OfficeProgressEvent[]
  document?: OfficeDocument
  error?: OfficeOperationError
}

export async function fetchOfficeStatus(): Promise<OfficeStatus> {
  return request<OfficeStatus>('/api/reins/office/status')
}

export async function fetchOfficeDocuments(limit = 25): Promise<{ documents: OfficeDocument[] }> {
  return request<{ documents: OfficeDocument[] }>(`/api/reins/office/documents?limit=${limit}`)
}

export async function fetchOfficeSkills(format?: OfficeFormat): Promise<{ skills: OfficeSkill[] }> {
  const query = format ? `?format=${encodeURIComponent(format)}` : ''
  return request<{ skills: OfficeSkill[] }>(`/api/reins/office/skills${query}`)
}

export async function createOfficeDocument(input: OfficeCreateInput): Promise<{ document: OfficeDocument }> {
  return request<{ document: OfficeDocument }>('/api/reins/office/documents', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function reviseOfficeDocument(
  documentId: string,
  instruction: string,
): Promise<{ document: OfficeDocument }> {
  return request<{ document: OfficeDocument }>(
    `/api/reins/office/documents/${encodeURIComponent(documentId)}/revisions`,
    {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    },
  )
}

export async function startOfficeCreateOperation(
  input: OfficeCreateInput,
): Promise<{ operation: OfficeOperation }> {
  return request<{ operation: OfficeOperation }>('/api/reins/office/operations', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function startOfficeRevisionOperation(
  documentId: string,
  instruction: string,
): Promise<{ operation: OfficeOperation }> {
  return request<{ operation: OfficeOperation }>(
    `/api/reins/office/documents/${encodeURIComponent(documentId)}/revision-operations`,
    {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    },
  )
}

export async function fetchOfficeOperation(operationId: string): Promise<{ operation: OfficeOperation }> {
  return request<{ operation: OfficeOperation }>(
    `/api/reins/office/operations/${encodeURIComponent(operationId)}`,
  )
}

export function getOfficePreviewUrl(documentId: string, version = ''): string {
  const params = new URLSearchParams()
  const token = getApiKey()
  const profile = getActiveProfileName()
  if (token) params.set('token', token)
  if (profile) params.set('profile', profile)
  if (version) params.set('v', version)
  const query = params.toString()
  return `${getBaseUrlValue()}/api/reins/office/documents/${encodeURIComponent(documentId)}/preview${query ? `?${query}` : ''}`
}

export async function fetchOfficePreviewHtml(documentId: string): Promise<string> {
  const params = new URLSearchParams()
  const profile = getActiveProfileName()
  if (profile) params.set('profile', profile)
  const query = params.toString()
  const url = `${getBaseUrlValue()}/api/reins/office/documents/${encodeURIComponent(documentId)}/preview${query ? `?${query}` : ''}`
  const token = getApiKey()
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    const responseBody = await response.text().catch(() => '')
    let detail = responseBody.trim()
    try {
      const payload = JSON.parse(responseBody) as { error?: unknown, message?: unknown }
      detail = String(payload.error || payload.message || '').trim()
    } catch {}
    throw new Error(detail || `Office preview failed (${response.status})`)
  }
  return response.text()
}
