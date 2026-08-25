export interface WeComWorkflow {
  statusText: string;
  toolPreview: string;
  steps: Array<{ id: string; label: string }>;
  instructions: string[];
}

export const WECOM_WORKFLOW_TOOL_NAME = 'wecom_workflow';

/**
 * This workflow is for the NEW project plan:
 *
 * WeChat Customer Service / 微信客服 is handled by the VPS-side wechat_kf system.
 * Reins does NOT handle WeChat callbacks, resident chat, FAQ, or AI customer-service replies.
 *
 * Reins only handles structured Enterprise WeChat / WeCom ticket notifications:
 * - receive the WeCom bot/group text notification
 * - parse ticket_id/category/priority/resident_ref/summary/source/created_at
 * - validate ticket_id / external_id
 * - record Excel ledger
 * - classify and assign responsible role
 * - notify staff
 * - update same ticket when staff reply
 * - generate progress/closure report
 */

const WECOM_RE =
  /\b(?:wecom|enterprise\s+wechat|wechat|weixin|we\s*chat)\b|企业微信|企微|微信/i;

const WORK_ORDER_ACTION_RE =
  /\b(?:ticket|work\s*order|workorder|order|record|excel|report|assign|assignment|notify|notification|staff|reply|update|status|complaint|intake)\b|(?:工单|记录|报告|报表|分配|指派|通知|员工|工作人员|回复|更新|状态|投诉|录入|台账)/i;

const READ_ONLY_RE =
  /\b(?:summary|summarize|count|list|show|find|detail|report|export)\b|(?:汇总|总结|统计|查询|查看|列出|详情|报告|报表|台账|导出)/i;

const MUTATION_RE =
  /\b(?:receive|ingest|intake|save|record|notify|assign|reply|update)\b|(?:接收|录入|保存|记录|通知|分配|指派|回复|更新|处理结果)/i;

const NON_TASK_RE =
  /^(?:section|integration|feature|design|settings?|config(?:uration)?|docs?|page|route)\b/i;

function compactInput(input: string): string {
  return input.replace(/\s+/g, ' ').trim();
}

/**
 * Detect whether the request should enable the Reins WeCom work-order workflow.
 *
 * Important:
 * - This should NOT trigger for generic WeChat customer-service chatbot tasks.
 * - This should trigger when the request is about Enterprise WeChat / WeCom tickets,
 *   work orders, Excel records, reports, staff assignment, or staff reply updates.
 */
export function mayNeedWeComWorkflow(input: string): boolean {
  const text = compactInput(input);
  if (!text || !WECOM_RE.test(text)) return false;

  const remainingText = text.replace(WECOM_RE, '').trim();
  if (NON_TASK_RE.test(remainingText)) return false;
  if (READ_ONLY_RE.test(text) && !MUTATION_RE.test(text)) return false;

  return WORK_ORDER_ACTION_RE.test(text);
}

export function buildWeComWorkflow(input: string): WeComWorkflow | null {
  const request = compactInput(input);
  if (!mayNeedWeComWorkflow(request)) return null;

  return {
    statusText:
      '正在使用 Reins 工单流程校验通知内容、写入同一工单记录并通知负责人员。',

    toolPreview:
      '正在解析企业微信工单通知并更新本地工单台账',

    steps: [
      {
        id: 'receive_ticket_text',
        label: '接收企业微信中的结构化工单通知',
      },
      {
        id: 'parse_ticket_text',
        label: '解析工单编号、分类、优先级、诉求、来源和创建时间',
      },
      {
        id: 'validate_ticket',
        label: '校验工单编号和必填信息',
      },
      {
        id: 'record_idempotently',
        label: '按工单编号创建或更新同一条本地记录',
      },
      {
        id: 'classify_assign',
        label: '识别工单类型并分配负责部门',
      },
      {
        id: 'write_excel',
        label: '校验成功后更新 Excel 工单台账',
      },
      {
        id: 'notify_staff',
        label: '本地记录成功后通知负责人员',
      },
      {
        id: 'update_from_reply',
        label: '收到处理回复后更新同一张工单',
      },
      {
        id: 'generate_report',
        label: '根据真实工单记录生成进度或结案报告',
      },
      {
        id: 'human_review',
        label: '信息不完整或分类不确定时转为人工审核',
      },
    ],

    instructions: [
      '[已请求 Reins 企业微信工单流程]',
      `用户原始请求：${request}`,

      'Use the NEW project boundary: WeChat Customer Service / 微信客服 is handled by the VPS-side wechat_kf system, not by Reins.',
      'Do not implement or expect WeChat Customer Service callbacks inside Reins.',
      'Do not treat Reins as the resident-facing chatbot.',
      'Do not use generic desktop WeChat automation or computer_use for this workflow.',
      'Do not use any legacy or external agent gateway as the resident conversation handler for this workflow.',

      'Reins receives the documented WeCom bot/group ticket notification text produced by the VPS wechat_kf system.',
      'The expected text block starts with `[WeChat Customer-Service Ticket]` and includes ticket_id, category, priority, resident_ref, summary, source, and created_at.',
      'Use the native wecom_ingest_group_ticket tool to parse and save one complete structured notification.',
      'Use ticket_id/external_id as the idempotency key. Repeated ticket notifications must update the same local record and must not create duplicate Excel rows.',
      'Notify the assigned responsible role only after the local Excel-backed record write succeeds.',
      'Responsible-role notification uses configured Enterprise WeChat webhook/API environment variables such as REINS_WECOM_NOTIFY_WEBHOOK_PROPERTY, REINS_WECOM_NOTIFY_WEBHOOK_CLEANING, REINS_WECOM_NOTIFY_WEBHOOK_POLICE, REINS_WECOM_NOTIFY_WEBHOOK_HOSPITAL, REINS_WECOM_NOTIFY_WEBHOOK_COMMUNITY, or REINS_WECOM_NOTIFY_WEBHOOK_DEFAULT.',

      'For staff follow-up replies, use the native wecom_record_staff_reply tool.',
      'A staff reply must update the existing ticket by external_id/ticket_id instead of creating a new ticket.',
      'If the ticket ID or handling result is missing, ask the user for that information in concise Chinese instead of using a terminal or returning a technical error.',
      'Do not run shell commands, install packages, read SQLite directly, or use another document/work-order implementation as a fallback.',
      'Do not mark a ticket completed before the Excel update succeeds.',
      'If the payload is malformed, duplicated, or ambiguous, return a clear result and preserve enough evidence for diagnosis.',
      'If classification is uncertain, set the ticket to waiting_human_review and notify the default/human-review target.',
      'Keep enough execution evidence to explain what was received, validated, classified, written, notified, updated, or failed.',
    ],
  };
}

export function weComWorkflowToolArgs(
  workflow: WeComWorkflow,
  originalRequest: string,
): Record<string, unknown> {
  return {
    workflow: 'reins_wecom_work_order_intake',
    original_request: compactInput(originalRequest),

    desktop_computer_use: false,
    resident_chat_handler: false,
    wechat_customer_service_callback: false,

    transport: '来自 VPS wechat_kf 或企业微信桥接服务的结构化工单通知',

    preferred_native_tools: [
      'wecom_ingest_group_ticket',
      'wecom_record_staff_reply',
      'wecom_list_work_orders',
      'wecom_get_work_order',
      'wecom_work_order_report',
      'wecom_export_work_orders_excel',
      'wecom_work_order_doctor',
    ],

    decision_flow: [
      '接收结构化企业微信工单通知。',
      '解析并校验工单字段，尤其是 ticket_id/external_id。',
      '使用 ticket_id/external_id 作为幂等键。',
      '创建或更新同一条本地工单记录。',
      '识别分类并分配负责部门。',
      '更新 Excel 工单台账。',
      '本地写入成功后再通知负责人员。',
      '工作人员回复后更新同一条工单并追加处理结果。',
      '数据不完整或分类不确定时转为人工审核。',
    ],

    steps: workflow.steps.map((step, index) => ({
      order: index + 1,
      id: step.id,
      label: step.label,
    })),
  };
}

export function weComWorkflowToolResult(args: {
  workflow: WeComWorkflow;
  status: 'completed' | 'failed';
  finalOutput?: string;
  error?: string | null;
}): string {
  return JSON.stringify(
    {
      workflow: 'reins_wecom_work_order_intake',
      status: args.status,

      desktop_computer_use: false,
      resident_chat_handler: false,
      wechat_customer_service_callback: false,

      records_guard:
        'Reins stores structured work-order payloads idempotently by ticket_id/external_id and updates the Excel-backed ledger before staff notification.',
      boundary_guard:
        'WeChat Customer Service callbacks, resident chat, FAQ, and LLM customer-service replies belong to the VPS wechat_kf system, not Reins.',
      idempotency_guard:
        'Repeated ticket notifications must update the same local ticket record and must not create duplicate Excel rows.',
      notification_guard:
        'Responsible staff notification should happen only after the local record write succeeds.',
      review_guard:
        'Malformed, ambiguous, or uncertain tickets should be marked waiting_human_review instead of being silently discarded.',

      steps: args.workflow.steps.map((step, index) => ({
        order: index + 1,
        id: step.id,
        label: step.label,
      })),

      final_output: args.finalOutput || '',
      error: args.error || null,
    },
    null,
    2,
  );
}
