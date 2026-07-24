import {
  getApiKey,
  getBaseUrlValue,
  request,
} from '../client'

export interface WorkOrderRecord {
  id: number
  external_id: string
  created_at: string
  updated_at: string
  status: string
  priority: string
  category: string
  assigned_role: string
  assigned_role_label: string
  assignees: string[]
  location: string
  title: string
  issue: string
  customer_assessment: string
  handling_requirements: string
  resident_contact: string
  notification_status: string
  notification_channel: string
  notification_error: string
  result: string
  responder: string
  source_channel: string
  upstream_status: string
  assignment_reason: string
}

export interface WorkOrderFilterOptions {
  statuses: string[]
  priorities: string[]
  roles: Array<{ value: string; label: string }>
  categories: string[]
  notification_statuses: string[]
}

export interface WorkOrderExportInfo {
  available: boolean
  file_name: string
  updated_at: string
  visible_path: string
}

export interface WorkOrderSummary {
  database_exists: boolean
  total: number
  pending: number
  processing: number
  urgent: number
  notification_failed: number
  completed: number
  last_updated: string
  filters: WorkOrderFilterOptions
  export: WorkOrderExportInfo
}

export interface WorkOrderListResponse {
  records: WorkOrderRecord[]
  total: number
  limit: number
  offset: number
}

export interface WorkOrderQueryParams {
  search?: string
  status?: string
  priority?: string
  role?: string
  category?: string
  notification_status?: string
  limit?: number
  offset?: number
}

function toSearchParams(params: WorkOrderQueryParams): URLSearchParams {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.set(key, String(value))
  })
  return search
}

export async function fetchWorkOrderSummary(): Promise<WorkOrderSummary> {
  return request<WorkOrderSummary>('/api/hermes/work-orders/summary')
}

export async function fetchWorkOrders(
  params: WorkOrderQueryParams = {},
): Promise<WorkOrderListResponse> {
  const search = toSearchParams(params)
  return request<WorkOrderListResponse>(
    `/api/hermes/work-orders?${search.toString()}`,
  )
}

export async function fetchWorkOrder(id: number): Promise<WorkOrderRecord> {
  const response = await request<{ record: WorkOrderRecord }>(
    `/api/hermes/work-orders/${id}`,
  )
  return response.record
}

function downloadName(contentDisposition: string | null): string {
  const encoded = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (!encoded) return 'community-work-orders.xlsx'
  try {
    return decodeURIComponent(encoded)
  } catch {
    return 'community-work-orders.xlsx'
  }
}

export async function downloadWorkOrdersExcel(): Promise<string> {
  const headers: Record<string, string> = {}
  const apiKey = getApiKey()
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`
  const response = await fetch(
    `${getBaseUrlValue()}/api/hermes/work-orders/export`,
    {
      headers,
    },
  )
  if (!response.ok) {
    const message = await response.text().catch(() => '')
    throw new Error(message || `Export failed (${response.status})`)
  }

  const blob = await response.blob()
  const fileName = downloadName(response.headers.get('Content-Disposition'))
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  return fileName
}
