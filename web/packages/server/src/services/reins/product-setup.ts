import { execFile } from 'child_process'
import { existsSync } from 'fs'
import { delimiter, resolve } from 'path'
import { promisify } from 'util'
import { logger } from '../logger'
import { resolveReinsHome } from './reins-path'
import { resolveReinsWorkspaceRoot } from './workspace-path'

const execFileAsync = promisify(execFile)
let productSetupInFlight: Promise<Record<string, unknown> | null> | null = null

interface ReinsSetupInvocation {
  command: string
  argsPrefix: string[]
  cwd?: string
  pythonPath?: string
}

export function resolveReinsSetupInvocation(): ReinsSetupInvocation {
  const explicit = process.env.REINS_BIN?.trim()
  if (explicit) return { command: explicit, argsPrefix: [] }

  const roots = new Set([
    process.env.REINS_PROJECT_ROOT?.trim(),
    process.env.REINS_RUNTIME_ROOT?.trim(),
    resolve(process.cwd(), '..'),
    process.cwd(),
  ].filter(Boolean) as string[])

  const launcherNames = process.platform === 'win32'
    ? ['reins-runtime.exe', 'reins-runtime']
    : ['reins-runtime', 'reins-runtime.exe']

  for (const root of roots) {
    for (const launcherName of launcherNames) {
      const launcher = resolve(root, 'bin', launcherName)
      if (existsSync(launcher)) {
        return { command: launcher, argsPrefix: [] }
      }
    }
  }

  for (const root of roots) {
    const python = process.platform === 'win32'
      ? resolve(root, '.venv', 'Scripts', 'python.exe')
      : resolve(root, '.venv', 'bin', 'python')
    if (existsSync(python) && existsSync(resolve(root, 'src', 'reins'))) {
      return {
        command: python,
        argsPrefix: ['-m', 'reins.main'],
        cwd: root,
        pythonPath: resolve(root, 'src'),
      }
    }
  }

  const legacyExplicit = process.env.HERMES_BIN?.trim()
  if (legacyExplicit) {
    return { command: legacyExplicit, argsPrefix: [] }
  }

  throw new Error(
    'The local Reins runtime was not found. Restart the desktop app after rebuilding it, or reinstall the latest Reins release.',
  )
}

async function runReinsProductSetup(): Promise<Record<string, unknown> | null> {
  try {
    const invocation = resolveReinsSetupInvocation()
    const args = ['bootstrap', '--json']
    if (process.env.REINS_DESKTOP === '1') args.push('--enable-background-wecom')
    const { stdout } = await execFileAsync(invocation.command, [...invocation.argsPrefix, ...args], {
      cwd: invocation.cwd,
      env: {
        ...process.env,
        REINS_HOME: resolveReinsHome(),
        HERMES_HOME: resolveReinsHome(),
        REINS_WORKSPACE_ROOT: resolveReinsWorkspaceRoot(),
        ...(invocation.pythonPath
          ? { PYTHONPATH: [invocation.pythonPath, process.env.PYTHONPATH].filter(Boolean).join(delimiter) }
          : {}),
      },
      encoding: 'utf8',
      maxBuffer: 4 * 1024 * 1024,
      timeout: 60_000,
      windowsHide: true,
    })
    const result = JSON.parse(String(stdout || '{}')) as Record<string, unknown>
    logger.info({ product: 'Reins' }, '[bootstrap] Reins product features ready')
    return result
  } catch (error) {
    logger.warn(error, '[bootstrap] Reins product feature setup failed')
    return null
  }
}

export async function ensureReinsProductReady(): Promise<Record<string, unknown> | null> {
  if (!productSetupInFlight) productSetupInFlight = runReinsProductSetup()
  try {
    return await productSetupInFlight
  } finally {
    productSetupInFlight = null
  }
}
