import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { delimiter, dirname, join } from 'path'

type UpdateControllerMocks = {
  execFileSync: ReturnType<typeof vi.fn>
  spawn: ReturnType<typeof vi.fn>
  unref: ReturnType<typeof vi.fn>
  existsSync: ReturnType<typeof vi.fn>
  readFileSync: ReturnType<typeof vi.fn>
  mkdirSync: ReturnType<typeof vi.fn>
  writeFileSync: ReturnType<typeof vi.fn>
}

async function loadUpdateController(overrides: Partial<UpdateControllerMocks> = {}) {
  const execFileSync = overrides.execFileSync ?? vi.fn().mockReturnValue('updated')
  const unref = overrides.unref ?? vi.fn()
  const spawn = overrides.spawn ?? vi.fn(() => ({ unref, on: vi.fn() }))
  const existsSync = overrides.existsSync ?? vi.fn(() => true)
  const readFileSync = overrides.readFileSync ?? vi.fn(() => '{}')
  const mkdirSync = overrides.mkdirSync ?? vi.fn()
  const writeFileSync = overrides.writeFileSync ?? vi.fn()

  vi.resetModules()
  vi.doMock('child_process', () => ({ execFileSync, spawn }))
  vi.doMock('fs', () => ({ existsSync, readFileSync, mkdirSync, writeFileSync }))

  const mod = await import('../../packages/server/src/controllers/update')
  return {
    ...mod,
    mocks: { execFileSync, spawn, unref, existsSync, readFileSync, mkdirSync, writeFileSync },
  }
}

function createMockCtx() {
  return {
    status: 200,
    body: null as unknown,
  }
}

function getNodeBinDir() {
  return dirname(process.execPath)
}

function getNodePrefix() {
  return process.platform === 'win32' ? getNodeBinDir() : dirname(getNodeBinDir())
}

function getNpmCliPath() {
  const prefix = getNodePrefix()
  return process.platform === 'win32'
    ? join(prefix, 'node_modules', 'npm', 'bin', 'npm-cli.js')
    : join(prefix, 'lib', 'node_modules', 'npm', 'bin', 'npm-cli.js')
}

function getGlobalCliScript(prefix: string) {
  return process.platform === 'win32'
    ? join(prefix, 'node_modules', 'hermes-web-ui', 'bin', 'hermes-web-ui.mjs')
    : join(prefix, 'lib', 'node_modules', 'hermes-web-ui', 'bin', 'hermes-web-ui.mjs')
}

describe('update controller', () => {
  const originalPort = process.env.PORT
  const exitSpy = vi.spyOn(process, 'exit').mockImplementation((() => undefined) as never)

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    delete process.env.REINS_UPDATE_SERVICE
    delete process.env.REINS_UPDATE_TASK_NAME
    delete process.env.REINS_UPDATE_POWERSHELL
    delete process.env.REINS_HOME
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.doUnmock('child_process')
    vi.doUnmock('fs')
    if (originalPort === undefined) {
      delete process.env.PORT
    } else {
      process.env.PORT = originalPort
    }
    delete process.env.REINS_UPDATE_SERVICE
    delete process.env.REINS_UPDATE_TASK_NAME
    delete process.env.REINS_UPDATE_POWERSHELL
    delete process.env.REINS_HOME
  })

  it('queues the installed Linux updater instead of running the npm updater', async () => {
    process.env.REINS_UPDATE_SERVICE = 'reins-update.service'
    process.env.REINS_HOME = '/home/test/.reins'
    const { handleUpdate, mocks } = await loadUpdateController({
      existsSync: vi.fn(() => false),
    })
    const ctx = createMockCtx()

    await handleUpdate(ctx)

    expect(mocks.execFileSync).toHaveBeenCalledWith(
      'systemctl',
      ['--user', 'start', '--no-block', 'reins-update.service'],
      expect.objectContaining({ windowsHide: true }),
    )
    expect(mocks.writeFileSync).toHaveBeenCalledWith(
      '/home/test/.reins/logs/update-status.json',
      expect.stringContaining('"status":"requested"'),
      'utf-8',
    )
    expect(ctx.status).toBe(202)
    expect(ctx.body).toEqual({ success: true, message: 'Reins update started' })
  })

  it('queues the installed Windows updater task through PowerShell', async () => {
    process.env.REINS_UPDATE_TASK_NAME = 'Reins Updater'
    process.env.REINS_UPDATE_POWERSHELL = 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe'
    process.env.REINS_HOME = 'C:\\Users\\test\\AppData\\Local\\reins'
    const { handleUpdate, mocks } = await loadUpdateController({
      existsSync: vi.fn(() => false),
    })
    const ctx = createMockCtx()

    await handleUpdate(ctx)

    expect(mocks.execFileSync).toHaveBeenCalledWith(
      process.env.REINS_UPDATE_POWERSHELL,
      expect.arrayContaining([
        '-NonInteractive',
        '-Command',
        "Start-ScheduledTask -TaskName 'Reins Updater'",
      ]),
      expect.objectContaining({ windowsHide: true }),
    )
    expect(ctx.status).toBe(202)
  })

  it('updates and restarts through the running Node executable, not PATH shims', async () => {
    process.env.PORT = '9129'
    const nodeBinDir = getNodeBinDir()
    const npmCli = getNpmCliPath()
    const globalPrefix = getNodePrefix()
    const cliScript = getGlobalCliScript(globalPrefix)
    const execFileSync = vi.fn((_command: string, args: string[]) => {
      if (args[1] === 'root') {
        return process.platform === 'win32'
          ? join(globalPrefix, 'node_modules')
          : join(globalPrefix, 'lib', 'node_modules')
      }
      return 'updated'
    })
    const { handleUpdate, mocks } = await loadUpdateController({ execFileSync })
    const ctx = createMockCtx()

    await handleUpdate(ctx)

    expect(mocks.execFileSync).toHaveBeenCalledWith(
      process.execPath,
      [npmCli, 'install', '-g', 'hermes-web-ui@latest'],
      expect.objectContaining({
        encoding: 'utf-8',
        timeout: 10 * 60 * 1000,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
        env: expect.objectContaining({
          npm_node_execpath: process.execPath,
          PATH: expect.stringContaining(`${nodeBinDir}${delimiter}`),
        }),
      }),
    )
    expect(ctx.body).toEqual({ success: true, message: 'updated' })

    vi.runAllTimers()

    expect(mocks.execFileSync).toHaveBeenCalledWith(
      process.execPath,
      [npmCli, 'root', '-g'],
      expect.objectContaining({
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
        env: expect.objectContaining({ npm_node_execpath: process.execPath }),
      }),
    )
    expect(mocks.spawn).toHaveBeenCalledWith(
      process.execPath,
      [cliScript, 'restart', '--port', '9129'],
      expect.objectContaining({
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
        env: expect.objectContaining({ npm_node_execpath: process.execPath }),
      }),
    )
    expect(mocks.unref).toHaveBeenCalledOnce()
  })

  it('falls back to the default port when PORT is not set', async () => {
    delete process.env.PORT
    const { handleUpdate, mocks } = await loadUpdateController()
    const ctx = createMockCtx()

    await handleUpdate(ctx)
    vi.runAllTimers()

    expect(mocks.spawn).toHaveBeenCalledWith(
      process.execPath,
      [expect.any(String), 'restart', '--port', '8648'],
      expect.objectContaining({ detached: true, stdio: 'ignore', windowsHide: true }),
    )
  })

  it('does not log a restart error when the restart helper exits successfully', async () => {
    const handlers = new Map<string, (...args: any[]) => void>()
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const unref = vi.fn()
    const restart = {
      unref,
      on: vi.fn((event: string, handler: (...args: any[]) => void) => {
        handlers.set(event, handler)
        return restart
      }),
    }
    const spawn = vi.fn(() => restart)
    const { handleUpdate } = await loadUpdateController({ spawn, unref })
    const ctx = createMockCtx()

    await handleUpdate(ctx)
    vi.runAllTimers()
    handlers.get('exit')?.(0, null)

    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('returns a 500 with stderr when installation fails', async () => {
    const execFileSync = vi.fn(() => {
      const error = new Error('install failed') as Error & { stderr?: string }
      error.stderr = 'engine mismatch'
      throw error
    })
    const { handleUpdate, mocks } = await loadUpdateController({ execFileSync })
    const ctx = createMockCtx()

    await handleUpdate(ctx)

    expect(ctx.status).toBe(500)
    expect(ctx.body).toEqual({ success: false, message: 'engine mismatch' })
    expect(mocks.spawn).not.toHaveBeenCalled()
    expect(exitSpy).not.toHaveBeenCalled()
  })

})
