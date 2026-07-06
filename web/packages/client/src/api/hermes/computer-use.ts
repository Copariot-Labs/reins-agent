import { request } from '../client'

export interface ComputerUseCheck {
  ok: boolean
  command: string[]
  profile: string
  stdout: string
  stderr: string
  json?: unknown
  error?: string
}

export function fetchComputerUseStatus(): Promise<ComputerUseCheck> {
  return request<ComputerUseCheck>('/api/reins/computer-use/status')
}

export function fetchComputerUseDoctor(): Promise<ComputerUseCheck> {
  return request<ComputerUseCheck>('/api/reins/computer-use/doctor')
}
