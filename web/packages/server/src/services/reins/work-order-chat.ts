import {
  getWorkOrderSummary,
  listWorkOrders,
  parseWorkOrderQuery,
  type WorkOrderRecord,
} from '../hermes/work-orders'

const WORK_ORDER_RE = /(?:工单|工單|事项单|报修单|投诉单)|\b(?:work\s*orders?|workorders?|tickets?)\b/i
const WORK_ORDER_ACTION_RE = /(?:汇总|总结|统计|查询|查看|列出|详情|待处理|处理中|紧急|完成|关闭|报告|报表|台账|导出|更新|回复|跟进|处理结果|分配|指派)|\b(?:summary|summarize|count|list|show|find|detail|pending|urgent|completed|report|export|update|reply|assign)\b/i
const META_REQUEST_RE = /(?:功能|页面|界面|代码|实现|开发|设计|路由|接口|插件|测试|文档)|\b(?:feature|page|section|code|implement|develop|design|route|endpoint|plugin|test|documentation)\b/i
const PHONE_RE = /(?<!\d)1[3-9]\d{9}(?!\d)/g

function compact(value: string): string {
  return value.replace(/\s+/g, ' ').trim()
}

export function mayNeedWorkOrderChat(input: string): boolean {
  const text = compact(input)
  if (!text || !WORK_ORDER_RE.test(text)) return false
  if (META_REQUEST_RE.test(text) && !WORK_ORDER_ACTION_RE.test(text)) return false
  return WORK_ORDER_ACTION_RE.test(text)
}

export function isNativeWorkOrderExportRequest(input: string): boolean {
  const text = compact(input)
  if (!mayNeedWorkOrderChat(text)) return false
  const exportAction = /(?:导出|下载)|\b(?:export|download)\b/i.test(text)
  const workbook = /(?:Excel|xlsx|工作簿|电子表格|表格|台账)|\b(?:excel|xlsx|workbook|spreadsheet|ledger)\b/i.test(text)
  return exportAction && workbook
}

export function reinsWorkOrderAgentInstructions(): string {
  return [
    '[Reins Work Orders chat policy]',
    '工单查询、汇总、详情、更新、导出和报告必须使用 Reins 原生工单工具，不得自行编写脚本或使用通用文件工具代替。',
    '查询列表使用 wecom_list_work_orders；汇总统计使用 wecom_work_order_report；单张详情使用 wecom_get_work_order。',
    '导出 Excel 台账使用 wecom_export_work_orders_excel；记录工作人员处理结果使用 wecom_record_staff_reply。',
    '只有收到完整的企业微信结构化新工单通知时，才使用 wecom_ingest_group_ticket。配置诊断使用 wecom_work_order_doctor。',
    '用户未说明日期范围时，先按全部现有记录回答，并明确统计范围；不要为了可选筛选条件阻塞简单查询。',
    '更新工单时若缺少工单编号或处理结果，先用简短中文向用户询问缺失信息，不要返回技术错误。',
    '查询不存在的工单时，说明未找到并请用户核对编号；不得猜测或新建替代工单。',
    '需要制作 Word、Excel 或 PPT 工单报告时，必须先读取真实工单数据，再交给 Reins Office；不得编造记录、数量或处理结果。',
    '不得使用终端、Python 临时脚本、直接读取 SQLite、安装第三方包或调用非 Reins 工单方案作为后备路径。',
    '面向用户的进度、追问、结果和错误默认使用简体中文，并隐藏居民标识、联系方式、密钥和通知地址。',
  ].join('\n')
}

function safeText(value: unknown): string {
  return String(value || '').replace(PHONE_RE, '[已隐藏联系方式]').trim()
}

function officeSafeRecord(record: WorkOrderRecord) {
  return {
    id: record.id,
    external_id: record.external_id,
    created_at: record.created_at,
    updated_at: record.updated_at,
    status: record.status,
    priority: record.priority,
    category: record.category,
    assigned_role: record.assigned_role,
    assigned_role_label: record.assigned_role_label,
    assignees: record.assignees.map(safeText),
    location: safeText(record.location),
    title: safeText(record.title),
    issue: safeText(record.issue),
    handling_requirements: safeText(record.handling_requirements),
    notification_status: record.notification_status,
    result: safeText(record.result),
    responder: safeText(record.responder),
    source_channel: record.source_channel,
    assignment_reason: safeText(record.assignment_reason),
  }
}

export function buildWorkOrderOfficePrompt(input: string): string {
  if (!mayNeedWorkOrderChat(input)) return input

  const summary = getWorkOrderSummary()
  const list = listWorkOrders(parseWorkOrderQuery({ limit: 100 }))
  const source = {
    generated_at: new Date().toISOString(),
    scope: '当前 Reins 本地工单库；统计覆盖全部记录，明细按更新时间倒序最多提供 100 条',
    database_exists: summary.database_exists,
    summary: {
      total: summary.total,
      pending: summary.pending,
      processing: summary.processing,
      urgent: summary.urgent,
      notification_failed: summary.notification_failed,
      completed: summary.completed,
      last_updated: summary.last_updated,
    },
    records_total: list.total,
    records_truncated: list.total > list.records.length,
    records: list.records.map(officeSafeRecord),
  }

  return [
    input,
    '',
    '[Reins 工单报告真实数据]',
    '以下 JSON 来自当前 Reins 本地工单库。仅根据这些数据制作文件，不得虚构数量、工单、日期、负责人或处理结果。',
    '默认使用简体中文。不要在文件中写入居民标识、联系方式、密钥、Webhook 或内部技术说明。',
    '若明细被截断，应在报告的数据说明中明确披露；汇总数字仍覆盖全部工单。',
    JSON.stringify(source, null, 2),
  ].join('\n')
}
