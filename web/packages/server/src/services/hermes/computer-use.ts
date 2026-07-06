import { execFile } from 'child_process'
import { promisify } from 'util'
import { getHermesBin } from './hermes-path'
import { getProfileDir } from './hermes-profile'

const execFileAsync = promisify(execFile)
const COMMAND_TIMEOUT_MS = 15_000

export interface ComputerUseCheck {
  ok: boolean
  command: string[]
  profile: string
  stdout: string
  stderr: string
  json?: unknown
  error?: string
}

function candidateCommands(): Array<{ bin: string; args: string[] }> {
  const explicitReins = process.env.REINS_BIN?.trim()
  const explicitHermes = process.env.HERMES_BIN?.trim()
  const candidates: Array<{ bin: string; args: string[] }> = []
  if (explicitReins) candidates.push({ bin: explicitReins, args: ['computer-use'] })
  candidates.push({ bin: 'reins', args: ['computer-use'] })
  if (explicitHermes) candidates.push({ bin: explicitHermes, args: ['computer-use'] })
  candidates.push({ bin: getHermesBin(), args: ['computer-use'] })

  const seen = new Set<string>()
  return candidates.filter((candidate) => {
    const key = [candidate.bin, ...candidate.args].join('\0')
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function parseJson(raw: string): unknown | undefined {
  const text = raw.trim()
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function isCommandMissing(err: any): boolean {
  return err?.code === 'ENOENT'
}

async function runComputerUseCommand(profile: string, subcommand: 'status' | 'doctor'): Promise<ComputerUseCheck> {
  let lastError: any = null
  for (const candidate of candidateCommands()) {
    const command = [candidate.bin, ...candidate.args, subcommand]
    try {
      const { stdout, stderr } = await execFileAsync(candidate.bin, [...candidate.args, subcommand], {
        timeout: COMMAND_TIMEOUT_MS,
        windowsHide: true,
        maxBuffer: 1024 * 1024,
        env: {
          ...process.env,
          HERMES_HOME: getProfileDir(profile),
        },
      })
      return {
        ok: true,
        command,
        profile,
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        json: parseJson(stdout),
      }
    } catch (err: any) {
      lastError = err
      if (isCommandMissing(err)) continue
      return {
        ok: false,
        command,
        profile,
        stdout: String(err?.stdout || '').trim(),
        stderr: String(err?.stderr || '').trim(),
        json: parseJson(String(err?.stdout || '')),
        error: err?.message || String(err),
      }
    }
  }

  return {
    ok: false,
    command: ['reins', 'computer-use', subcommand],
    profile,
    stdout: '',
    stderr: '',
    error: lastError?.message || 'computer-use CLI command was not found',
  }
}

export function getComputerUseStatus(profile = 'default'): Promise<ComputerUseCheck> {
  return runComputerUseCommand(profile, 'status')
}

export function getComputerUseDoctor(profile = 'default'): Promise<ComputerUseCheck> {
  return runComputerUseCommand(profile, 'doctor')
}
