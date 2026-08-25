import { chmodSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

describe('Reins product setup invocation', () => {
  const originalEnv = { ...process.env }
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'reins-product-setup-'))
    process.env = { ...originalEnv }
    delete process.env.REINS_BIN
    delete process.env.HERMES_BIN
    delete process.env.REINS_RUNTIME_ROOT
  })

  afterEach(() => {
    process.env = { ...originalEnv }
    rmSync(tempDir, { recursive: true, force: true })
  })

  it('uses the project virtual environment when no Reins command is on PATH', async () => {
    const projectRoot = join(tempDir, 'reins-project')
    const python = process.platform === 'win32'
      ? join(projectRoot, '.venv', 'Scripts', 'python.exe')
      : join(projectRoot, '.venv', 'bin', 'python')
    mkdirSync(join(projectRoot, 'src', 'reins'), { recursive: true })
    mkdirSync(join(projectRoot, '.venv', process.platform === 'win32' ? 'Scripts' : 'bin'), { recursive: true })
    writeFileSync(python, '#!/bin/sh\n')
    chmodSync(python, 0o755)
    process.env.REINS_PROJECT_ROOT = projectRoot

    const { resolveReinsSetupInvocation } = await import('../../packages/server/src/services/reins/product-setup')
    const invocation = resolveReinsSetupInvocation()

    expect(invocation).toEqual({
      command: python,
      argsPrefix: ['-m', 'reins.main'],
      cwd: projectRoot,
      pythonPath: join(projectRoot, 'src'),
    })
  })
})
