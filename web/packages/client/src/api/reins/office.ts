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

export interface OfficeCreateInput {
  format: OfficeFormat
  prompt: string
  title?: string
  language?: string
  presentation?: OfficePresentationOptions
}

export interface OfficeStatus {
  available: boolean
  error: string | null
  setup_hint: string
  reins_available: boolean
  documents: number
}

export async function fetchOfficeStatus(): Promise<OfficeStatus> {
  return request<OfficeStatus>('/api/reins/office/status')
}

export async function fetchOfficeDocuments(limit = 25): Promise<{ documents: OfficeDocument[] }> {
  return request<{ documents: OfficeDocument[] }>(`/api/reins/office/documents?limit=${limit}`)
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
    const detail = await response.text().catch(() => '')
    throw new Error(`Office preview failed (${response.status})${detail ? `: ${detail}` : ''}`)
  }
  return response.text()
}
