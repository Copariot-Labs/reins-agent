import { execFile } from 'child_process'
import { promisify } from 'util'
import { logger } from '../logger'
import { resolveReinsHome } from './reins-path'

const execFileAsync = promisify(execFile)

function resolveReinsBin(): string {
  return process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim() || 'reins'
}

export async function ensureReinsProductReady(): Promise<Record<string, unknown> | null> {
  try {
    const args = ['bootstrap', '--json']
    if (process.env.REINS_DESKTOP === '1') args.push('--enable-background-wecom')
    const { stdout } = await execFileAsync(resolveReinsBin(), args, {
      env: {
        ...process.env,
        REINS_HOME: resolveReinsHome(),
        HERMES_HOME: resolveReinsHome(),
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
