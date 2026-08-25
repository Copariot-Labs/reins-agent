import {
  createOfficeDocument,
  reviseOfficeDocument,
  type OfficeDocumentDto,
  type OfficeFormat,
  type OfficeWorkerProgress,
} from './office'
export { officeRevisionNeedsClarification } from './office-clarification'

export type OfficeChatWorkTool =
  | 'document'
  | 'spreadsheet'
  | 'slides'
  | 'research'
  | 'browser'

export interface OfficeChatResult {
  handled: boolean
  message: string
  exit_code: number
  document: OfficeDocumentDto | null
  operation?: 'create' | 'revise'
  needs_clarification?: boolean
}

export type OfficeChatRequest =
  | { operation: 'create'; format: OfficeFormat }
  | { operation: 'revise'; document: OfficeDocumentDto }

export interface OfficeChatHistoryMessage {
  role?: string
  content?: string
  tool_name?: string | null
}

export type OfficeChatProgressReporter = (progress: OfficeWorkerProgress) => void

export const REINS_OFFICE_CREATE_TOOL = 'reins_office_create'
export const REINS_OFFICE_REVISE_TOOL = 'reins_office_revise'
export const OFFICE_CHAT_TOOL_NAMES = [
  REINS_OFFICE_CREATE_TOOL,
  REINS_OFFICE_REVISE_TOOL,
  'create_office_document',
  'revise_office_document',
] as const

const CREATE_PATTERN = /\b(create|make|generate|write|prepare|draft|build|compose|produce|design)\b/i
const OFFICE_PATTERN = /\b(document|docx?|letter|application|report|proposal|summary|resume|cv|notice|program|plan|minutes|memo|policy|agreement|contract|statement|certificate|form|invoice|receipt|agenda|presentation|pptx?|slides?|slide deck|deck|powerpoint|spreadsheet|excel|xlsx|sheets?|table|ledger|tracker|budget|inventory|roster)\b/i
const QUESTION_PATTERN = /^(how\s+to\s+|how\s+can\s+i\s+|what\s+is\s+|why\s+|can\s+you\s+explain\s+)/i
const CHINESE_CREATE_PATTERN = /(创建|制作|生成|写一份|撰写|准备|起草|做一个)/
const CHINESE_OFFICE_PATTERN = /(文档|报告|通知|申请|合同|简历|计划|方案|表格|电子表格|工作簿|演示文稿|幻灯片|PPT)/i
const REVISE_PATTERN = /\b(edit|modify|revise|update|change|adjust|add|insert|append|remove|delete|replace|rename|fix|correct|improve|rewrite|reformat|restyle|redesign|recolor|resize|reorder|move|swap|apply|extend|expand|shorten|simplify|polish|refresh|format|bold|italicize|underline|highlight|align|merge|sort|filter)\b/i
const REFERENCED_REVISION_PATTERN = /\b(make|turn)\s+(it|this|that|(?:the\s+)?(?:file|document|workbook|spreadsheet|presentation|deck|title|heading|text|table|chart|slide|sheet|page|row|column|cell))\b/i
const OFFICE_FORMATTING_PATTERN = /\b(set|use|calculate)\b.{0,80}\b(it|this|that|title|heading|text|table|chart|slide|sheet|page|row|column|cell|value|formula|total|color|palette|font|theme|layout|design|margin|spacing)\b/i
const CHINESE_REVISE_PATTERN = /(编辑|修改|更新|更改|调整|添加|插入|删除|移除|替换|重命名|修复|改进|重写|重新设计|换色|移动|润色|扩展|精简)/
const NEW_OFFICE_FILE_PATTERN = /\b(?:create|make|generate|prepare|build|design)?\s*(?:a\s+)?(?:new|another|separate|different|second)\s+(?:office\s+)?(?:file|document|docx?|workbook|spreadsheet|excel|xlsx|presentation|powerpoint|pptx?|deck)\b/i
const CHINESE_NEW_OFFICE_FILE_PATTERN = /(新建|另外|另一个|单独|第二个).{0,8}(文档|文件|表格|工作簿|演示文稿|幻灯片|PPT)/i
const OFFICE_TOOL_NAMES = new Set<string>(OFFICE_CHAT_TOOL_NAMES)

function selectedFormat(workTool?: OfficeChatWorkTool): OfficeFormat | null {
  if (workTool === 'document') return 'docx'
  if (workTool === 'spreadsheet') return 'xlsx'
  if (workTool === 'slides') return 'pptx'
  return null
}

function normalizedReference(value: unknown): string {
  return String(value || '').trim().replace(/\\/g, '/').toLocaleLowerCase()
}

function documentTimestamp(document: OfficeDocumentDto): number {
  const parsed = Date.parse(document.updated_at || document.created_at || '')
  return Number.isFinite(parsed) ? parsed : 0
}

export function resolveIndexedOfficeRevisionDocument(
  message: string,
  documents: OfficeDocumentDto[],
  workTool?: OfficeChatWorkTool,
): OfficeDocumentDto | null {
  if (!hasOfficeRevisionIntent(message)) return null
  const selected = selectedFormat(workTool)
  const candidates = documents.filter(document => !selected || document.kind === selected)
  if (candidates.length === 0) return null

  const reference = normalizedReference(message)
  const ranked = candidates.map(document => {
    const id = normalizedReference(document.id)
    const path = normalizedReference(document.path)
    const fileName = normalizedReference(document.file_name)
    const title = normalizedReference(document.title)
    let score = 0
    if (id && reference.includes(id)) score = Math.max(score, 100)
    if (path && reference.includes(path)) score = Math.max(score, 90)
    if (fileName && reference.includes(fileName)) score = Math.max(score, 80)
    if (title && title.length >= 3 && reference.includes(title)) score = Math.max(score, 70)
    return { document, score }
  }).sort((left, right) => (
    right.score - left.score
    || documentTimestamp(right.document) - documentTimestamp(left.document)
  ))

  if (ranked[0].score > 0) return ranked[0].document

  // An explicit unmatched Office filename should never silently revise another file.
  if (/[^\s/\\]+\.(?:docx|xlsx|pptx)\b/i.test(message)) return null
  return ranked[0].document
}

export function officeClarificationPrompt(
  request: OfficeChatRequest,
  userMessage: string,
): string {
  const useChinese = /[\u3400-\u9fff]/.test(userMessage)
  if (request.operation === 'revise') {
    const title = request.document.title || request.document.file_name
    return useChinese
      ? `为了准确修改《${title}》，请再告诉我：要修改哪个部分、希望改成什么内容或样式，以及哪些内容必须保持不变。例如：“把标题改为红色，将第二部分扩写为三段，其他内容保持不变。”`
      : `To revise “${title}” accurately, please tell me which section to change, what content or style you want, and what must remain unchanged. For example: “Make the title red, expand section two to three paragraphs, and keep everything else unchanged.”`
  }
  return useChinese
    ? '为了生成可直接使用的文件，请再告诉我文件用途、必须包含的主要内容，以及期望的格式或风格。'
    : 'To create a usable file, please provide its purpose, the main content it must include, and the format or style you prefer.'
}

export function inferOfficeChatFormat(
  message: string,
  workTool?: OfficeChatWorkTool,
): OfficeFormat | null {
  const selected = selectedFormat(workTool)
  if (selected) return selected

  const text = String(message || '').toLowerCase()
  if (/\b(spreadsheet|excel|xlsx|workbook|sheets?|ledger|tracker|budget|inventory|roster)\b/i.test(text)
    || /(表格|电子表格|工作簿)/.test(text)) return 'xlsx'
  if (/\b(presentation|pptx?|slides?|slide deck|deck|powerpoint)\b/i.test(text)
    || /(演示文稿|幻灯片|PPT)/i.test(text)) return 'pptx'
  if (OFFICE_PATTERN.test(text) || CHINESE_OFFICE_PATTERN.test(text)) return 'docx'
  return null
}

export function mayNeedOfficeChat(
  message: string,
  workTool?: OfficeChatWorkTool,
): boolean {
  const text = String(message || '').trim()
  if (!text || text.startsWith('/')) return false
  if (selectedFormat(workTool)) return true
  if (QUESTION_PATTERN.test(text.toLowerCase())) return false
  return (CREATE_PATTERN.test(text) && OFFICE_PATTERN.test(text))
    || (CHINESE_CREATE_PATTERN.test(text) && CHINESE_OFFICE_PATTERN.test(text))
}

function officeDocumentFromToolContent(content: string | undefined): OfficeDocumentDto | null {
  if (!content) return null
  try {
    const parsed = JSON.parse(content) as { office_document?: OfficeDocumentDto | null }
    const document = parsed.office_document
    return document?.id && document.path ? document : null
  } catch {
    return null
  }
}

function pendingOfficeClarificationDocument(
  messages: OfficeChatHistoryMessage[],
): OfficeDocumentDto | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role !== 'tool' || !OFFICE_TOOL_NAMES.has(String(message.tool_name || ''))) continue
    try {
      const parsed = JSON.parse(message.content || '') as {
        needs_clarification?: boolean
        office_document?: OfficeDocumentDto | null
      }
      return parsed.needs_clarification && parsed.office_document?.id
        ? parsed.office_document
        : null
    } catch {
      return null
    }
  }
  return null
}

export function latestOfficeChatDocument(
  messages: OfficeChatHistoryMessage[],
): OfficeDocumentDto | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.role !== 'tool' || !OFFICE_TOOL_NAMES.has(String(message.tool_name || ''))) {
      continue
    }
    const document = officeDocumentFromToolContent(message.content)
    if (document) return document
  }
  return null
}

export function mayNeedOfficeRevision(
  message: string,
  document: OfficeDocumentDto | null,
  workTool?: OfficeChatWorkTool,
): boolean {
  const text = String(message || '').trim()
  if (!document || !hasOfficeRevisionIntent(text)) return false

  const selected = selectedFormat(workTool)
  if (selected && selected !== document.kind) return false

  return true
}

export function hasOfficeRevisionIntent(message: string): boolean {
  const text = String(message || '').trim()
  if (!text || text.startsWith('/')) return false
  if (NEW_OFFICE_FILE_PATTERN.test(text) || CHINESE_NEW_OFFICE_FILE_PATTERN.test(text)) {
    return false
  }

  return REVISE_PATTERN.test(text)
    || REFERENCED_REVISION_PATTERN.test(text)
    || OFFICE_FORMATTING_PATTERN.test(text)
    || CHINESE_REVISE_PATTERN.test(text)
}

export function resolveOfficeChatRequest(
  message: string,
  workTool?: OfficeChatWorkTool,
  messages: OfficeChatHistoryMessage[] = [],
): OfficeChatRequest | null {
  const document = latestOfficeChatDocument(messages)
  const clarificationDocument = pendingOfficeClarificationDocument(messages)
  const cancelledClarification = /^(?:cancel|never mind|nevermind|stop|不用了?|取消|算了|停止)[.!。！\s]*$/i.test(message.trim())
  if (
    clarificationDocument
    && !cancelledClarification
    && !NEW_OFFICE_FILE_PATTERN.test(message)
    && !CHINESE_NEW_OFFICE_FILE_PATTERN.test(message)
    && (!selectedFormat(workTool) || selectedFormat(workTool) === clarificationDocument.kind)
  ) {
    return { operation: 'revise', document: clarificationDocument }
  }
  if (mayNeedOfficeRevision(message, document, workTool) && document) {
    return { operation: 'revise', document }
  }
  if (!mayNeedOfficeChat(message, workTool)) return null

  const format = inferOfficeChatFormat(message, workTool)
  return format ? { operation: 'create', format } : null
}

export async function runOfficeChatRequest(
  message: string,
  request: OfficeChatRequest,
  officeSkillId?: string,
  onProgress?: OfficeChatProgressReporter,
  signal?: AbortSignal,
): Promise<OfficeChatResult> {
  const prompt = String(message || '').trim()
  if (request.operation === 'revise') {
    const revisionInput = {
      instruction: prompt,
    }
    const document = onProgress || signal
      ? await reviseOfficeDocument(request.document.id, revisionInput, onProgress, signal)
      : await reviseOfficeDocument(request.document.id, revisionInput)
    return {
      handled: true,
      message: 'Office document updated successfully.',
      exit_code: 0,
      document,
      operation: 'revise',
    }
  }

  const createInput = {
    format: request.format,
    prompt,
    language: /[\u3400-\u9fff]/.test(prompt) ? 'zh' : 'en',
    ...(officeSkillId ? { skill_id: officeSkillId } : {}),
  }
  const document = onProgress || signal
    ? await createOfficeDocument(createInput, onProgress, signal)
    : await createOfficeDocument(createInput)
  return {
    handled: true,
    message: 'Office document created successfully.',
    exit_code: 0,
    document,
    operation: 'create',
  }
}

export async function createOfficeChatDocument(
  message: string,
  workTool?: OfficeChatWorkTool,
  officeSkillId?: string,
  onProgress?: OfficeChatProgressReporter,
  signal?: AbortSignal,
): Promise<OfficeChatResult> {
  const prompt = String(message || '').trim()
  if (!mayNeedOfficeChat(prompt, workTool)) {
    return { handled: false, message: '', exit_code: 0, document: null }
  }

  const format = inferOfficeChatFormat(prompt, workTool)
  if (!format) {
    return {
      handled: true,
      message: 'Choose Documents, Spreadsheets, or Slides and try again.',
      exit_code: 1,
      document: null,
    }
  }

  return runOfficeChatRequest(
    prompt,
    { operation: 'create', format },
    officeSkillId,
    onProgress,
    signal,
  )
}
