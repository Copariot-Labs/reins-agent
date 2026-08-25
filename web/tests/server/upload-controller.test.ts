import { Readable } from 'stream'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mkdirMock = vi.hoisted(() => vi.fn())
const writeFileMock = vi.hoisted(() => vi.fn())

vi.mock('fs/promises', async () => {
  const actual = await vi.importActual<typeof import('fs/promises')>('fs/promises')
  return {
    ...actual,
    mkdir: mkdirMock,
    writeFile: writeFileMock,
  }
})

vi.mock('../../packages/server/src/services/hermes/hermes-profile', () => ({
  getActiveProfileName: vi.fn(() => 'default'),
}))

vi.mock('../../packages/server/src/services/hermes/upload-paths', () => ({
  getProfileUploadDir: vi.fn(() => '/tmp/Reins Workspace/Inbox'),
}))

function multipartBody(boundary: string, name: string, content: string): Buffer {
  return Buffer.from([
    `--${boundary}`,
    `Content-Disposition: form-data; name="file"; filename="${name}"`,
    'Content-Type: text/plain',
    '',
    content,
    `--${boundary}--`,
    '',
  ].join('\r\n'))
}

describe('upload controller', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mkdirMock.mockResolvedValue(undefined)
    writeFileMock.mockResolvedValue(undefined)
  })

  it('stores chat uploads with readable names in the shared native Inbox', async () => {
    const boundary = 'test-boundary'
    const { handleUpload } = await import('../../packages/server/src/controllers/upload')
    const ctx: any = {
      get: vi.fn((header: string) => header === 'content-type' ? `multipart/form-data; boundary=${boundary}` : ''),
      req: Readable.from([multipartBody(boundary, 'note.txt', 'hello')]),
      state: { profile: { name: 'research' } },
      body: undefined,
      status: 200,
    }

    await handleUpload(ctx)

    expect(mkdirMock).toHaveBeenCalledWith('/tmp/Reins Workspace/Inbox', { recursive: true })
    expect(writeFileMock).toHaveBeenCalledOnce()
    const [savedPath, data] = writeFileMock.mock.calls[0]
    expect(savedPath).toBe('/tmp/Reins Workspace/Inbox/note.txt')
    expect(data.toString('utf-8')).toBe('hello')
    expect(writeFileMock.mock.calls[0][2]).toEqual({ flag: 'wx' })
    expect(ctx.body.files[0]).toMatchObject({ name: 'note.txt', path: savedPath })
  })

  it('adds a number instead of overwriting an existing Inbox file', async () => {
    const boundary = 'test-boundary'
    const existsError = Object.assign(new Error('exists'), { code: 'EEXIST' })
    writeFileMock.mockRejectedValueOnce(existsError).mockResolvedValueOnce(undefined)
    const { handleUpload } = await import('../../packages/server/src/controllers/upload')
    const ctx: any = {
      get: vi.fn((header: string) => header === 'content-type' ? `multipart/form-data; boundary=${boundary}` : ''),
      req: Readable.from([multipartBody(boundary, 'note.txt', 'updated')]),
      state: { profile: { name: 'default' } },
      body: undefined,
      status: 200,
    }

    await handleUpload(ctx)

    expect(writeFileMock.mock.calls[0][0]).toBe('/tmp/Reins Workspace/Inbox/note.txt')
    expect(writeFileMock.mock.calls[1][0]).toBe('/tmp/Reins Workspace/Inbox/note-2.txt')
    expect(ctx.body.files[0].path).toBe('/tmp/Reins Workspace/Inbox/note-2.txt')
  })
})
