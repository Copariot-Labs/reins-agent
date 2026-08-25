import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { createServer, type Server } from 'net'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('agent bridge manager command resolution', () => {
  const originalEnv = { ...process.env }
  let tempDir = ''

  beforeEach(() => {
    vi.resetModules()
    tempDir = mkdtempSync(join(tmpdir(), 'hermes-agent-bridge-manager-'))
    process.env = { ...originalEnv }
    delete process.env.HERMES_AGENT_ROOT
    delete process.env.HERMES_AGENT_BRIDGE_PYTHON
    delete process.env.HERMES_AGENT_BRIDGE_UV
    delete process.env.UV
  })

  afterEach(() => {
    process.env = { ...originalEnv }
    if (tempDir) rmSync(tempDir, { recursive: true, force: true })
  })

  it('uses the installed hermes command Python when no source root exists', async () => {
    const binDir = join(tempDir, 'bin')
    const homeDir = join(tempDir, 'home')
    const fakePython = join(binDir, 'python')
    const fakeHermes = join(binDir, 'hermes')
    mkdirSync(binDir, { recursive: true })
    mkdirSync(homeDir, { recursive: true })
    writeFileSync(fakePython, '#!/bin/sh\n')
    chmodSync(fakePython, 0o755)
    writeFileSync(fakeHermes, `#!${fakePython}\n`)
    chmodSync(fakeHermes, 0o755)
    process.env.HERMES_HOME = homeDir
    process.env.HERMES_BIN = fakeHermes

    const { resolveAgentBridgeCommand } = await import('../../packages/server/src/services/hermes/agent-bridge/manager')
    const command = resolveAgentBridgeCommand()

    expect(command).toEqual({
      command: fakePython,
      argsPrefix: [],
      agentRoot: undefined,
      hermesHome: homeDir,
    })
  })

  it('discovers hermes-agent from a global lib install next to the hermes command', async () => {
    const installDir = join(tempDir, 'usr', 'local')
    const binDir = join(installDir, 'bin')
    const agentRoot = join(installDir, 'lib', 'hermes-agent')
    const fakePython = join(binDir, 'python')
    const fakeHermes = join(binDir, 'hermes')
    const homeDir = join(tempDir, 'home')
    mkdirSync(binDir, { recursive: true })
    mkdirSync(agentRoot, { recursive: true })
    mkdirSync(homeDir, { recursive: true })
    writeFileSync(join(agentRoot, 'run_agent.py'), '')
    writeFileSync(fakePython, '#!/bin/sh\n')
    chmodSync(fakePython, 0o755)
    writeFileSync(fakeHermes, `#!${fakePython}\n`)
    chmodSync(fakeHermes, 0o755)
    process.env.HERMES_HOME = homeDir
    process.env.HERMES_BIN = fakeHermes

    const { resolveAgentBridgeCommand } = await import('../../packages/server/src/services/hermes/agent-bridge/manager')
    const command = resolveAgentBridgeCommand()

    expect(command.agentRoot).toBe(agentRoot)
  })

  it('falls back to system Python instead of uv when no source root exists', async () => {
    const homeDir = join(tempDir, 'home')
    const fakePython = join(tempDir, 'python3')
    mkdirSync(homeDir, { recursive: true })
    writeFileSync(fakePython, '#!/bin/sh\n')
    chmodSync(fakePython, 0o755)
    process.env.HERMES_HOME = homeDir
    process.env.HERMES_BIN = join(tempDir, 'missing-hermes')
    process.env.PYTHON = fakePython

    const { resolveAgentBridgeCommand } = await import('../../packages/server/src/services/hermes/agent-bridge/manager')
    const command = resolveAgentBridgeCommand()

    expect(command).toEqual({
      command: fakePython,
      argsPrefix: [],
      agentRoot: undefined,
      hermesHome: homeDir,
    })
  })

  it('injects Web UI OpenRouter attribution into the bridge process env by default', async () => {
    const { buildAgentBridgeProcessEnv } = await import('../../packages/server/src/services/hermes/agent-bridge/manager')
    const env = buildAgentBridgeProcessEnv('ipc:///tmp/test.sock', '/tmp/hermes-home', '/tmp/hermes-agent', '/tmp/Reins Workspace')

    expect(env.HERMES_OPENROUTER_APP_REFERER).toBe('https://ekkolearnai.com')
    expect(env.HERMES_OPENROUTER_APP_TITLE).toBe('Hermes Web UI')
    expect(env.HERMES_OPENROUTER_APP_CATEGORIES).toBe('cli-agent,personal-agent')
    expect(env.REINS_WORKSPACE_ROOT).toBe('/tmp/Reins Workspace')
    expect(env.TERMINAL_CWD).toBe('/tmp/Reins Workspace')
    expect(env.REINS_HOME).toBe('/tmp/hermes-home')
    expect(env.REINS_REQUIRED_TOOLSETS).toContain('reins_finance')
  })

  it('uses the Reins project runtime when launched directly from the web workspace', async () => {
    const projectRoot = join(tempDir, 'reins-project')
    const agentRoot = join(projectRoot, 'vendor', 'hermes-agent')
    const projectPython = process.platform === 'win32'
      ? join(projectRoot, '.venv', 'Scripts', 'python.exe')
      : join(projectRoot, '.venv', 'bin', 'python3')
    mkdirSync(join(projectRoot, 'src', 'reins'), { recursive: true })
    mkdirSync(agentRoot, { recursive: true })
    mkdirSync(join(projectRoot, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin'), { recursive: true })
    writeFileSync(join(agentRoot, 'run_agent.py'), '')
    writeFileSync(projectPython, '#!/bin/sh\n')
    chmodSync(projectPython, 0o755)
    delete process.env.HERMES_HOME
    delete process.env.HERMES_BIN
    process.env.REINS_HOME = join(tempDir, 'reins-home')

    const { buildAgentBridgeProcessEnv, resolveAgentBridgeCommand } = await import('../../packages/server/src/services/hermes/agent-bridge/manager')
    const command = resolveAgentBridgeCommand({ reinsProjectRoot: projectRoot })
    const env = buildAgentBridgeProcessEnv(
      'ipc:///tmp/test.sock',
      command.hermesHome,
      command.agentRoot,
      '/tmp/Reins Workspace',
      command.reinsProjectRoot,
    )

    expect(command.command).toBe(projectPython)
    expect(command.agentRoot).toBe(agentRoot)
    expect(command.hermesHome).toBe(join(tempDir, 'reins-home'))
    expect(env.PYTHONPATH).toContain(join(projectRoot, 'src'))
    expect(env.REINS_RUNTIME_ROOT).toBe(projectRoot)
  })

  it('keeps explicit OpenRouter attribution env values when starting the bridge', async () => {
    process.env.HERMES_OPENROUTER_APP_REFERER = 'https://example.invalid/app'
    process.env.HERMES_OPENROUTER_APP_TITLE = 'Custom App'
    process.env.HERMES_OPENROUTER_APP_CATEGORIES = 'custom-category'

    const { buildAgentBridgeProcessEnv } = await import('../../packages/server/src/services/hermes/agent-bridge/manager')
    const env = buildAgentBridgeProcessEnv('ipc:///tmp/test.sock', '/tmp/hermes-home', undefined)

    expect(env.HERMES_OPENROUTER_APP_REFERER).toBe('https://example.invalid/app')
    expect(env.HERMES_OPENROUTER_APP_TITLE).toBe('Custom App')
    expect(env.HERMES_OPENROUTER_APP_CATEGORIES).toBe('custom-category')
  })

  it('uses an isolated default bridge endpoint while running under Vitest', async () => {
    const { DEFAULT_AGENT_BRIDGE_ENDPOINT } = await import('../../packages/server/src/services/hermes/agent-bridge/client')

    expect(DEFAULT_AGENT_BRIDGE_ENDPOINT).toContain(`hermes-agent-bridge-test-${process.pid}`)
    expect(DEFAULT_AGENT_BRIDGE_ENDPOINT).not.toBe('ipc:///tmp/hermes-agent-bridge.sock')
  })

  it('waits briefly for a restarting bridge socket before failing', async () => {
    const endpoint = process.platform === 'win32'
      ? `tcp://127.0.0.1:${32000 + (process.pid % 10000)}`
      : `ipc://${join(tempDir, 'late-bridge.sock')}`
    let server: Server | undefined

    const ready = new Promise<void>((resolve) => {
      setTimeout(() => {
        server = createServer((socket) => {
          socket.once('data', () => {
            socket.end(`${JSON.stringify({ ok: true, pong: true })}\n`)
          })
        })
        if (endpoint.startsWith('ipc://')) {
          server.listen(endpoint.slice('ipc://'.length), resolve)
        } else {
          const url = new URL(endpoint)
          server.listen(Number(url.port), url.hostname, resolve)
        }
      }, 150)
    })

    try {
      const { AgentBridgeClient } = await import('../../packages/server/src/services/hermes/agent-bridge/client')
      const client = new AgentBridgeClient({ endpoint, connectRetryMs: 1000, timeoutMs: 1000 })
      await expect(client.ping()).resolves.toMatchObject({ ok: true, pong: true })
      await ready
    } finally {
      await new Promise<void>((resolve) => server?.close(() => resolve()) ?? resolve())
    }
  })
})
