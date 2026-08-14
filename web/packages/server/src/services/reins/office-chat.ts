import {
  createOfficeDocument,
  type OfficeDocumentDto,
  type OfficeFormat,
} from './office'

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
}

const CREATE_PATTERN = /\b(create|make|generate|write|prepare|draft|build|compose|produce|design)\b/i
const OFFICE_PATTERN = /\b(document|docx?|letter|application|report|proposal|summary|resume|cv|notice|program|plan|minutes|memo|policy|agreement|contract|statement|certificate|form|invoice|receipt|agenda|presentation|pptx?|slides?|slide deck|deck|powerpoint|spreadsheet|excel|xlsx|sheets?|table|ledger|tracker|budget|inventory|roster)\b/i
const QUESTION_PATTERN = /^(how\s+to\s+|how\s+can\s+i\s+|what\s+is\s+|why\s+|can\s+you\s+explain\s+)/i
const CHINESE_CREATE_PATTERN = /(创建|制作|生成|写一份|撰写|准备|起草|做一个)/
const CHINESE_OFFICE_PATTERN = /(文档|报告|通知|申请|合同|简历|计划|方案|表格|电子表格|工作簿|演示文稿|幻灯片|PPT)/i

function selectedFormat(workTool?: OfficeChatWorkTool): OfficeFormat | null {
  if (workTool === 'document') return 'docx'
  if (workTool === 'spreadsheet') return 'xlsx'
  if (workTool === 'slides') return 'pptx'
  return null
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

export async function createOfficeChatDocument(
  message: string,
  workTool?: OfficeChatWorkTool,
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

  const document = await createOfficeDocument({
    format,
    prompt,
    language: /[\u3400-\u9fff]/.test(prompt) ? 'zh' : 'en',
  })
  return {
    handled: true,
    message: 'Office document created successfully.',
    exit_code: 0,
    document,
  }
}
