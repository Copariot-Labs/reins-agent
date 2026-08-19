import { beforeEach, describe, expect, it, vi } from 'vitest'

const request = vi.hoisted(() => vi.fn())

vi.mock('@/api/client', () => ({ request }))

import { checkHealth } from '@/api/hermes/system'

describe('system health API', () => {
  beforeEach(() => {
    request.mockReset()
    request.mockResolvedValue({ status: 'ok' })
  })

  it('uses the lightweight readiness endpoint for connection polling', async () => {
    await expect(checkHealth()).resolves.toEqual({ status: 'ok' })
    expect(request).toHaveBeenCalledWith('/health/ready')
  })
})
