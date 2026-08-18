// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/client', () => ({
  getActiveProfileName: () => 'default',
  getApiKey: () => 'token',
  getBaseUrlValue: () => '',
}))

import { downloadFile, saveBlob } from '@/api/hermes/download'

const originalCreateObjectUrl = URL.createObjectURL
const originalRevokeObjectUrl = URL.revokeObjectURL

describe('desktop downloads', () => {
  beforeEach(() => {
    delete (window as any).__TAURI_INTERNALS__
    vi.restoreAllMocks()
  })

  afterEach(() => {
    delete (window as any).__TAURI_INTERNALS__
    URL.createObjectURL = originalCreateObjectUrl
    URL.revokeObjectURL = originalRevokeObjectUrl
  })

  it('uses the Tauri save command for downloaded files', async () => {
    const invoke = vi.fn().mockResolvedValue(true)
    ;(window as any).__TAURI_INTERNALS__ = { invoke }
    const blob = {
      arrayBuffer: vi.fn().mockResolvedValue(Uint8Array.from([1, 2, 3]).buffer),
    } as unknown as Blob
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(blob),
    } as unknown as Response)

    await expect(downloadFile('/tmp/report.docx', 'report.docx')).resolves.toBe(true)

    expect(invoke).toHaveBeenCalledWith('save_download', {
      fileName: 'report.docx',
      bytes: [1, 2, 3],
    })
  })

  it('keeps browser downloads on the anchor-based web path', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:web-download')
    URL.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    await expect(saveBlob(new Blob(['report']), 'report.txt')).resolves.toBe(true)

    expect(click).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:web-download')
  })
})
