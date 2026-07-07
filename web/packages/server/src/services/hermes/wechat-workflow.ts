export interface WeChatWorkflow {
  statusText: string
  toolPreview: string
  steps: Array<{ id: string; label: string }>
  instructions: string[]
}

export const WECHAT_WORKFLOW_TOOL_NAME = 'wechat_workflow'

const WECHAT_APP_RE = /\b(?:wechat|weixin|we\s*chat)\b|微信/i
const ENGLISH_ACTION_RE = /\b(?:send|message|msg|dm|text|draft|prepare|write|forward|share|tell|notify|remind|open|focus|launch|search|find)\b/i
const CHINESE_ACTION_RE = /(?:发|发送|转发|分享|告诉|通知|提醒|打开|启动|搜索|查找|找人|联系人|消息)/
const ENGLISH_SHORTHAND_RE = /^(?:wechat|weixin|we\s*chat)\s+(.+)$/i
const NON_TASK_SHORTHAND_RE = /^(?:section|integration|feature|design|settings?|config(?:uration)?|docs?|page|route)\b/i

function compactInput(input: string): string {
  return input.replace(/\s+/g, ' ').trim()
}

export function mayNeedWeChatWorkflow(input: string): boolean {
  const text = compactInput(input)
  if (!text || !WECHAT_APP_RE.test(text)) return false
  return ENGLISH_ACTION_RE.test(text) || CHINESE_ACTION_RE.test(text) || looksLikeEnglishShorthand(text)
}

function looksLikeEnglishShorthand(text: string): boolean {
  const match = text.match(ENGLISH_SHORTHAND_RE)
  const rest = match?.[1]?.trim() || ''
  if (!rest || NON_TASK_SHORTHAND_RE.test(rest)) return false
  if (/[:：]/.test(rest)) return true
  return rest.split(/\s+/).length >= 2
}

export function buildWeChatWorkflow(input: string): WeChatWorkflow | null {
  const request = compactInput(input)
  if (!mayNeedWeChatWorkflow(request)) return null

  return {
    statusText: 'WeChat workflow enabled: use the deterministic Reins WeChat skill, draft first, and require confirmation before sending.',
    toolPreview: 'Research if needed, compose, use Reins WeChat skill to find contact and draft, then wait for send confirmation',
    steps: [
      { id: 'gather_info', label: 'Gather information with backend or visible browser when needed' },
      { id: 'prepare_message', label: 'Prepare the WeChat message from the gathered information' },
      { id: 'open_wechat', label: 'Open or focus WeChat with the deterministic Reins WeChat skill' },
      { id: 'find_contact', label: 'Search and select the requested WeChat contact with the Reins WeChat skill' },
      { id: 'draft_message', label: 'Draft the message or attachment with the Reins WeChat skill' },
      { id: 'confirm_send', label: 'Ask for confirmation before running a confirmed send command' },
    ],
    instructions: [
      '[WeChat desktop workflow requested]',
      `Original WeChat request: ${request}`,
      'Treat this as a personal WeChat/Weixin desktop task from the Web UI.',
      'Do not use generic Hermes computer_use to perform WeChat contact search, drafting, or sending as the primary path.',
      'Use the deterministic Reins WeChat skill/CLI for WeChat actions. Prefer `reins wechat draft --to "<contact>" --message "<message>" --json` to find the contact and draft the message without sending.',
      'If a Hermes plugin toolset named reins_wechat or tools named wechat_draft_message/wechat_send_current_draft are available, prefer those tools over terminal commands.',
      'If web research is needed before composing the message, use Hermes browser tools according to the selected browser mode, then return to the WeChat desktop workflow.',
      'Use generic computer_use only as a fallback for non-WeChat desktop research or if the deterministic WeChat skill reports that it cannot continue.',
      'Before any irreversible action, especially sending the drafted WeChat message or file, show the exact recipient and final message/attachment summary and request confirmation through the available approval or clarification flow.',
      'Do not run `reins wechat send --confirm`, `reins wechat send-current --confirm`, or any confirmed WeChat send tool until the user confirms in this run.',
      'If the contact, account, message, file, language, or target conversation is ambiguous, ask a clarification question instead of guessing.',
      'If WeChat is not installed, not logged in, the Reins WeChat skill dependencies are missing, or the deterministic skill cannot control the desktop, report the blocker and the next manual step. You may suggest `reins wechat doctor --json` for diagnostics.',
      'Keep the visible step trace clear: announce what you are checking or controlling before desktop actions, then summarize what was drafted or why the workflow stopped.',
    ],
  }
}

export function weChatWorkflowToolArgs(workflow: WeChatWorkflow, originalRequest: string): Record<string, unknown> {
  return {
    workflow: 'wechat_desktop_message',
    original_request: compactInput(originalRequest),
    confirmation_required_before_send: true,
    browser_strategy: [
      'Use backend browser/search for normal web research.',
      'Use the connected visible browser when the user selected visible browsing or asks to watch/control.',
      'Use deterministic Reins WeChat skill/CLI for WeChat contact search, drafting, and sending.',
      'Use generic computer use only for non-WeChat desktop research or as a fallback if the WeChat skill cannot continue.',
    ],
    preferred_skill_commands: [
      'reins wechat doctor --json',
      'reins wechat draft --to "<contact>" --message "<message>" --json',
      'reins wechat send-current --confirm --json',
    ],
    steps: workflow.steps.map((step, index) => ({
      order: index + 1,
      id: step.id,
      label: step.label,
    })),
  }
}

export function weChatWorkflowToolResult(args: {
  workflow: WeChatWorkflow
  status: 'completed' | 'failed'
  finalOutput?: string
  error?: string | null
}): string {
  return JSON.stringify({
    workflow: 'wechat_desktop_message',
    status: args.status,
    confirmation_required_before_send: true,
    send_guard: 'No WeChat message or file should be sent until the user confirms the exact recipient and final content.',
    steps: args.workflow.steps.map((step, index) => ({
      order: index + 1,
      id: step.id,
      label: step.label,
    })),
    final_output: args.finalOutput || '',
    error: args.error || null,
  }, null, 2)
}
