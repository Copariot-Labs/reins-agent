import { request } from '@/api/client'

export interface WeComSetupValues {
  ticket_api_url: string
  statuses: string
  ticket_limit: string
  poll_interval: string
  ticket_timeout: string
  reply_bot_name: string
  users_default: string
  users_property: string
  users_cleaning: string
  users_police: string
  users_hospital: string
  users_community: string
  users_human_review: string
  export_dir: string
  routing_mode: string
  routing_confidence: string
  routing_timeout: string
}

export interface WeComSetupStatus {
  configured: boolean
  ticket_api_token_configured: boolean
  group_webhook_configured: boolean
  values: WeComSetupValues
  background?: Record<string, unknown> | null
}

export interface WeComSetupInput extends Partial<WeComSetupValues> {
  ticket_api_token?: string
  group_webhook?: string
}

export function fetchWeComSetup(): Promise<WeComSetupStatus> {
  return request<WeComSetupStatus>('/api/reins/wecom/setup')
}

export function saveWeComSetup(values: WeComSetupInput): Promise<WeComSetupStatus> {
  return request<WeComSetupStatus>('/api/reins/wecom/setup', {
    method: 'POST',
    body: JSON.stringify(values),
  })
}
