// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/router', () => ({
  default: {
    currentRoute: { value: { name: 'login' } },
    replace: vi.fn(),
  },
}))

import { getBaseUrlValue, resolveApiBaseUrl } from '@/api/client'

describe('desktop API base URL', () => {
  afterEach(() => {
    delete (window as any).__TAURI_INTERNALS__
    localStorage.clear()
  })

  it('uses the Vite proxy inside Tauri development', () => {
    localStorage.setItem('hermes_server_url', 'https://stale.example.com')
    ;(window as any).__TAURI_INTERNALS__ = { invoke: vi.fn() }

    expect(getBaseUrlValue()).toBe('')
  })

  it('uses the bundled local service inside a packaged Tauri app', () => {
    expect(resolveApiBaseUrl({
      preview: false,
      desktop: true,
      development: false,
      configuredUrl: 'https://stale.example.com',
    })).toBe('http://127.0.0.1:8648')
  })

  it('keeps a configured server URL in the browser build', () => {
    expect(resolveApiBaseUrl({
      preview: false,
      desktop: false,
      development: true,
      configuredUrl: 'https://reins.example.com',
    })).toBe('https://reins.example.com')
  })
})
