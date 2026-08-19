// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockGetBaseUrlValue = vi.hoisted(() => vi.fn(() => 'http://127.0.0.1:8648'))

vi.mock('@/api/client', () => ({
  getBaseUrlValue: mockGetBaseUrlValue,
  request: vi.fn(),
}))

import { loginWithPassword } from '@/api/auth'

describe('desktop authentication API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockGetBaseUrlValue.mockReturnValue('http://127.0.0.1:8648')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends login to the bundled desktop service', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ token: 'desktop-token' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))
    vi.stubGlobal('fetch', fetchMock)

    await expect(loginWithPassword('admin', '123456')).resolves.toBe('desktop-token')
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8648/api/auth/login',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('replaces the raw HTML JSON error with a startup message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      '<!doctype html><html></html>',
      { status: 200, headers: { 'Content-Type': 'text/html' } },
    )))

    await expect(loginWithPassword('admin', '123456')).rejects.toThrow(
      'The local Reins service is still starting',
    )
  })
})
