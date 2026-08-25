import { spawn, type ChildProcess } from 'child_process'
import { once } from 'events'
import { existsSync } from 'fs'
import { delimiter, resolve } from 'path'
import { resolveReinsHome } from './reins-path'
import { resolveReinsWorkspaceRoot } from './workspace-path'

export const REINS_FINANCE_TOOL = 'reins_finance'
const FINANCE_TOOL_NAMES = new Set([
  REINS_FINANCE_TOOL,
  'finance_record_transaction',
  'finance_record_transaction_from_text',
])
const FINANCE_TIMEOUT_MS = 240_000

export function reinsFinanceAgentInstructions(): string {
  return [
    '[Reins Finance workflow]',
    'Handle finance requests through the native Reins Finance tools so the user can see normal reasoning and tool progress.',
    'Respond in Chinese by default when the user writes Chinese.',
    'Before recording a transaction, make sure the transaction type (income or expense), amount, and purpose/source are clear. Infer ordinary categories and today\'s date when reasonable, but never invent an amount or transaction type.',
    'If required information is missing or ambiguous, ask one concise Chinese clarification question and wait for the answer. Do not call a write tool until the answer is available.',
    'Use finance_record_transaction for structured data or finance_record_transaction_from_text for complete Chinese natural-language transactions.',
    'Use finance_list_transactions and finance_summarize_period for history and summaries.',
    'For every finance request, use only the native finance_* tools for finance data access or changes. Never use terminal commands, shell scripts, Python code or packages, direct database access, generic spreadsheet tools, or another document generator as a fallback.',
    'If the finance_* tools are unavailable, do not attempt the task another way. Briefly tell the user in Chinese that Reins Finance is temporarily unavailable and ask them to restart Reins, without exposing internal implementation names.',
    'For finance workbook requests, always use finance_export_excel.',
    'After a successful tool call, summarize what was recorded or found. For exports, include the returned workspace file path as a clickable link.',
  ].join('\n')
}

export interface FinanceChatHistoryMessage {
  role?: string
  content?: string
  tool_name?: string | null
}

export interface FinanceChatFile {
  path: string
  file_name: string
  kind: 'xlsx'
}

export interface FinanceChatResult {
  handled: boolean
  ok: boolean
  action: string
  raw_text: string
  message_zh?: string
  message_en?: string
  needs_clarification?: boolean
  pending_text?: string
  transaction?: Record<string, unknown>
  transactions?: Array<Record<string, unknown>>
  summary?: Record<string, unknown>
  file?: FinanceChatFile
  error?: string
}

interface ReinsInvocation {
  command: string
  argsPrefix: string[]
  cwd?: string
  pythonPath?: string
}

function resolveReinsInvocation(): ReinsInvocation {
  const explicit = process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim()
  if (explicit) return { command: explicit, argsPrefix: [] }

  const roots = new Set([
    process.env.REINS_PROJECT_ROOT?.trim(),
    resolve(process.cwd(), '..'),
    process.cwd(),
  ].filter(Boolean) as string[])
  for (const root of roots) {
    const python = process.platform === 'win32'
      ? resolve(root, '.venv', 'Scripts', 'python.exe')
      : resolve(root, '.venv', 'bin', 'python')
    if (existsSync(python)) {
      return {
        command: python,
        argsPrefix: ['-m', 'reins.main'],
        cwd: root,
        pythonPath: resolve(root, 'src'),
      }
    }
  }
  return { command: 'reins', argsPrefix: [] }
}

function terminateWorker(child: ChildProcess, signal: NodeJS.Signals) {
  if (process.platform !== 'win32' && child.pid) {
    try {
      process.kill(-child.pid, signal)
      return
    } catch {}
  }
  try {
    child.kill(signal)
  } catch {}
}

function parseWorkerResult(stdout: string): Record<string, unknown> {
  const text = stdout.trim()
  try {
    return JSON.parse(text) as Record<string, unknown>
  } catch {
    const start = text.indexOf('{')
    const end = text.lastIndexOf('}')
    if (start >= 0 && end > start) {
      return JSON.parse(text.slice(start, end + 1)) as Record<string, unknown>
    }
    throw new Error('Reins Finance returned an invalid response.')
  }
}

async function runFinanceProcess(
  args: string[],
  signal?: AbortSignal,
): Promise<Record<string, unknown>> {
  if (signal?.aborted) throw Object.assign(new Error('Finance operation cancelled.'), { code: 'worker_cancelled' })
  const invocation = resolveReinsInvocation()
  const reinsHome = resolveReinsHome()
  const child = spawn(
    invocation.command,
    [...invocation.argsPrefix, ...args],
    {
      cwd: invocation.cwd,
      env: {
        ...process.env,
        REINS_HOME: reinsHome,
        HERMES_HOME: process.env.HERMES_HOME?.trim() || reinsHome,
        REINS_WORKSPACE_ROOT: resolveReinsWorkspaceRoot(),
        ...(invocation.pythonPath
          ? { PYTHONPATH: [invocation.pythonPath, process.env.PYTHONPATH].filter(Boolean).join(delimiter) }
          : {}),
      },
      detached: process.platform !== 'win32',
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  )
  let stdout = ''
  let stderr = ''
  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')
  child.stdout.on('data', chunk => { stdout += String(chunk) })
  child.stderr.on('data', chunk => { stderr += String(chunk) })

  let forceKillTimer: NodeJS.Timeout | undefined
  let timeoutTimer: NodeJS.Timeout | undefined
  let terminated = false
  const terminate = () => {
    if (terminated) return
    terminated = true
    terminateWorker(child, 'SIGTERM')
    forceKillTimer = setTimeout(() => terminateWorker(child, 'SIGKILL'), 2_000)
    forceKillTimer.unref()
  }
  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    timeoutTimer = setTimeout(() => {
      terminate()
      reject(Object.assign(new Error('Finance operation timed out.'), { code: 'worker_timeout' }))
    }, FINANCE_TIMEOUT_MS)
  })
  let abortHandler: (() => void) | undefined
  const abortPromise = new Promise<never>((_resolve, reject) => {
    if (!signal) return
    abortHandler = () => {
      terminate()
      reject(Object.assign(new Error('Finance operation cancelled.'), { code: 'worker_cancelled' }))
    }
    signal.addEventListener('abort', abortHandler, { once: true })
  })

  try {
    const closePromise = once(child, 'close') as Promise<[number | null, NodeJS.Signals | null]>
    const errorPromise = once(child, 'error').then(([error]) => { throw error as Error })
    const [code] = await Promise.race([closePromise, errorPromise, timeoutPromise, abortPromise])
    const result = parseWorkerResult(stdout)
    if (code !== 0) {
      throw new Error(String(result.error || stderr.trim() || `Finance worker exited ${code}`))
    }
    return result
  } finally {
    if (timeoutTimer) clearTimeout(timeoutTimer)
    if (signal && abortHandler) signal.removeEventListener('abort', abortHandler)
    if (forceKillTimer) clearTimeout(forceKillTimer)
  }
}

export async function runFinanceChatWorker(
  text: string,
  signal?: AbortSignal,
): Promise<FinanceChatResult> {
  const result = await runFinanceProcess(['finance', 'chat-json', text], signal)
  return result as unknown as FinanceChatResult
}

export async function runFinanceWorkbookExport(
  query: {
    startDate?: string | null
    endDate?: string | null
    type?: 'income' | 'expense' | null
    category?: string | null
  },
  signal?: AbortSignal,
): Promise<{ path: string; fileName: string; count: number }> {
  if (!query.startDate || !query.endDate) {
    throw new Error('Finance export requires a start date and end date.')
  }

  const args = [
    'finance',
    'export-xlsx-json',
    '--start-date',
    query.startDate,
    '--end-date',
    query.endDate,
  ]
  if (query.type) args.push('--type', query.type)
  if (query.category) args.push('--category', query.category)

  const result = await runFinanceProcess(args, signal)
  if (result.ok !== true || typeof result.path !== 'string' || typeof result.fileName !== 'string') {
    throw new Error(String(result.error || 'Reins Finance could not generate the Excel workbook.'))
  }
  return {
    path: result.path,
    fileName: result.fileName,
    count: Number(result.count || 0),
  }
}

export function mayNeedFinanceChat(text: string): boolean {
  const value = String(text || '').trim()
  if (!value || !/[\u3400-\u9fff]/.test(value)) return false
  if (/(预算|模板|规划|计划|监控|预测)/.test(value) && /(表格|Excel|工作簿)/i.test(value)) return false
  const hasAmount = /\d+(?:\.\d+)?\s*(?:元|块|人民币)?/.test(value)
  const explicitRecord = /(记账|记一笔|记录(?:一笔)?|新增(?:一笔)?|添加(?:一笔)?|录入(?:一笔)?)/.test(value)
  const transactionAction = /(支付|付款|消费|收到|收款|进账|报销到账|退款)/.test(value)
  const transaction = explicitRecord
    || transactionAction
    || (hasAmount
      && /(收入|支出|买|花了?|打车|外卖|工资|奖金|早餐|午餐|晚餐|咖啡|奶茶|交通|地铁|公交|停车|加油|房租|水费|电费)/.test(value))
  const query = /(查|查询|查看|显示|列出|最近|明细|汇总|总结|统计|多少|情况|状况|余额|结余)/.test(value)
    && /(收入|支出|财务|收支|交易|流水|账单|记录)/.test(value)
  const naturalSummary = /(花了多少|赚了多少|余额|结余|收支情况|收支状况|财务情况|财务状况)/.test(value)
  const exportRequest = /(导出|下载|生成|制作|创建|保存)/.test(value)
    && /(Excel|xlsx|工作簿|电子表格|表格)/i.test(value)
    && /(财务|收支|交易|流水|账单|记账)/.test(value)
  return transaction || query || naturalSummary || exportRequest
}

export function pendingFinanceClarificationText(
  messages: FinanceChatHistoryMessage[],
): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role !== 'tool' || !FINANCE_TOOL_NAMES.has(String(message.tool_name || ''))) continue
    try {
      const parsed = JSON.parse(message.content || '') as FinanceChatResult
      return parsed.needs_clarification && parsed.pending_text
        ? String(parsed.pending_text).trim() || null
        : null
    } catch {
      return null
    }
  }
  return null
}

export function resolveFinanceChatText(
  input: string,
  messages: FinanceChatHistoryMessage[] = [],
): string | null {
  const text = String(input || '').trim()
  if (!text) return null
  const pending = pendingFinanceClarificationText(messages)
  if (pending && /^(?:取消|算了|不用了?|停止|cancel|never mind)[。.!！\s]*$/i.test(text)) return null
  const conciseContinuation = text.length <= 30 && (
    /^(?:这是?)?(?:收入|支出)[。.!！\s]*$/.test(text)
    || /^\d+(?:\.\d+)?\s*(?:元|块|人民币)?[。.!！\s]*$/.test(text)
  )
  if (pending && (!mayNeedFinanceChat(text) || conciseContinuation)) return `${pending} ${text}`
  return mayNeedFinanceChat(text) ? text : null
}

export function financeChatMessage(result: FinanceChatResult, preferChinese: boolean): string {
  const message = preferChinese
    ? String(result.message_zh || result.message_en || '')
    : String(result.message_en || result.message_zh || '')
  if (!result.file?.path) return message
  const label = preferChinese ? '打开财务 Excel 工作簿' : 'Open the finance Excel workbook'
  return `${message}\n\n[${label}](<${result.file.path.replace(/\\/g, '/')}>)`
}
