import { request } from '../client'

export interface VisibleBrowserStatus {
  connected: boolean
  cdpUrl?: string
  endpoint?: string
  browser?: string
  profile: string
  managed: boolean
  pid?: number
  error?: string
}

export function fetchVisibleBrowserStatus(): Promise<VisibleBrowserStatus> {
  return request<VisibleBrowserStatus>('/api/reins/browser/status')
}

export function connectVisibleBrowser(): Promise<VisibleBrowserStatus> {
  return request<VisibleBrowserStatus>('/api/reins/browser/connect', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function disconnectVisibleBrowser(): Promise<VisibleBrowserStatus> {
  return request<VisibleBrowserStatus>('/api/reins/browser/disconnect', {
    method: 'POST',
    body: JSON.stringify({}),
  })
}
