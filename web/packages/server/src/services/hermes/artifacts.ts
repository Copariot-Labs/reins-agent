import { execFile } from 'child_process'
import { promisify } from 'util'
import { logger } from '../logger'
import { resolveReinsHome as resolveDefaultReinsHome } from './reins-path'

const execFileAsync = promisify(execFile)
const DEFAULT_ARTIFACT_TIMEOUT_MS = 240000

export interface ArtifactChatPreprocessResult {
  handled: boolean
  message: string
  exit_code: number
  artifact?: Record<string, unknown> | null
}

const CREATE_PATTERN = /\b(create|make|generate|write|prepare|draft|build|compose|produce|design)\b/i
const ARTIFACT_PATTERN = /\b(document|docx?|letter|application|report|proposal|summary|resume|cv|notice|program|plan|minutes|memo|policy|agreement|contract|statement|certificate|form|invoice|receipt|agenda|presentation|pptx?|slides?|slide deck|deck|powerpoint|spreadsheet|excel|xlsx|sheets?|table|ledger|tracker|budget|inventory|roster)\b/i
const QUESTION_PATTERN = /^(how\s+to\s+|how\s+can\s+i\s+|what\s+is\s+|why\s+|can\s+you\s+explain\s+)/i

function resolveReinsBin(): string {
  return process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim() || 'reins'
}

function resolveReinsHome(): string {
  return resolveDefaultReinsHome()
}

function artifactTimeoutMs(): number {
  const raw = process.env.REINS_ARTIFACT_WEB_TIMEOUT_MS
  const value = raw ? Number(raw) : DEFAULT_ARTIFACT_TIMEOUT_MS
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_ARTIFACT_TIMEOUT_MS
}

export function mayNeedArtifactPreprocess(message: string): boolean {
  const text = String(message || '').trim()
  if (!text || text.startsWith('/')) return false
  if (QUESTION_PATTERN.test(text.toLowerCase())) return false
  return CREATE_PATTERN.test(text) && ARTIFACT_PATTERN.test(text)
}

function normalizePreprocessResult(value: any): ArtifactChatPreprocessResult | null {
  if (!value || typeof value !== 'object') return null
  return {
    handled: value.handled === true,
    message: typeof value.message === 'string' ? value.message : '',
    exit_code: Number.isFinite(Number(value.exit_code)) ? Number(value.exit_code) : 0,
    artifact: value.artifact && typeof value.artifact === 'object' ? value.artifact : null,
  }
}

function parsePreprocessOutput(stdout: unknown): ArtifactChatPreprocessResult | null {
  const text = String(stdout || '').trim()
  if (!text) return null

  try {
    return normalizePreprocessResult(JSON.parse(text))
  } catch {}

  const start = text.indexOf('{')
  const end = text.lastIndexOf('}')
  if (start < 0 || end <= start) return null

  try {
    return normalizePreprocessResult(JSON.parse(text.slice(start, end + 1)))
  } catch {
    return null
  }
}

export async function preprocessArtifactChatMessage(message: string): Promise<ArtifactChatPreprocessResult> {
  const cleanMessage = String(message || '').trim()
  if (!mayNeedArtifactPreprocess(cleanMessage)) {
    return { handled: false, message: '', exit_code: 0, artifact: null }
  }

  const reinsHome = resolveReinsHome()
  const env = {
    ...process.env,
    REINS_HOME: reinsHome,
    HERMES_HOME: process.env.HERMES_HOME?.trim() || reinsHome,
  }
  const args = [
    'artifacts',
    'preprocess-chat',
    '--message',
    cleanMessage,
    '--json',
  ]

  try {
    const { stdout, stderr } = await execFileAsync(resolveReinsBin(), args, {
      env,
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024,
      timeout: artifactTimeoutMs(),
      windowsHide: true,
    })
    if (String(stderr || '').trim()) {
      logger.warn('[artifacts] preprocess stderr: %s', String(stderr).trim())
    }
    const parsed = parsePreprocessOutput(stdout)
    if (!parsed) {
      throw new Error('Artifact preprocessor returned invalid JSON')
    }
    return parsed
  } catch (err: any) {
    const parsed = parsePreprocessOutput(err?.stdout)
    if (parsed) return parsed

    const stderr = String(err?.stderr || '').trim()
    const messageText = stderr || err?.message || String(err)
    throw new Error(messageText)
  }
}
