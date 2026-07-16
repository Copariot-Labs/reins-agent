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

  return WORK_ORDER_ACTION_RE.test(text);
}

export function buildWeComWorkflow(input: string): WeComWorkflow | null {
  const request = compactInput(input);
  if (!mayNeedWeComWorkflow(request)) return null;

  return {
    statusText:
      'Reins WeCom work-order workflow enabled: receive the documented WeCom ticket notification text from the VPS wechat_kf system, parse it, record it idempotently, classify and assign it, notify staff, update the same Excel-backed record from staff replies, and generate reports.',

    toolPreview:
      'Receive WeCom ticket notification text, parse ticket_id/category/priority/resident_ref/summary/source/created_at into JSON, call work-order add, notify staff, and update the Excel ledger.',

    steps: [
      {
        id: 'receive_ticket_text',
        label:
          'Receive the documented WeCom bot/group ticket notification text from VPS wechat_kf',
      },
      {
        id: 'parse_ticket_text',
        label:
          'Parse ticket_id, category, priority, resident_ref, summary, source, and created_at into JSON',
      },
      {
        id: 'validate_ticket',
        label:
          'Validate ticket_id/external_id, category, priority, resident reference, summary, and creation time',
      },
      {
        id: 'record_idempotently',
        label:
          'Create or update the local work-order record using ticket_id/external_id as the idempotency key',
      },
      {
        id: 'classify_assign',
        label:
          'Classify the ticket and assign it to property, cleaning, police, hospital, community, or human review',
      },
      {
        id: 'write_excel',
        label:
          'Write or update the Excel-backed work-order ledger only after validation succeeds',
      },
      {
        id: 'notify_staff',
        label:
          'Notify the responsible staff target through the configured Enterprise WeChat webhook/API after the local record write succeeds',
      },
      {
        id: 'update_from_reply',
        label:
          'Update the same local ticket record when responsible staff reply with progress, resolution, or escalation notes',
      },
      {
        id: 'generate_report',
        label:
          'Generate a progress report or closure report from the local ticket record and event history',
      },
      {
        id: 'human_review',
        label:
          'Mark malformed, ambiguous, or uncertain tickets as waiting_human_review instead of silently dropping them',
      },
    ],

    instructions: [
      '[Reins WeCom work-order workflow requested]',
      `Original request: ${request}`,

      'Use the NEW project boundary: WeChat Customer Service / 微信客服 is handled by the VPS-side wechat_kf system, not by Reins.',
      'Do not implement or expect WeChat Customer Service callbacks inside Reins.',
      'Do not treat Reins as the resident-facing chatbot.',
      'Do not use generic desktop WeChat automation or computer_use for this workflow.',
      'Do not use Hermes WeCom gateway as the resident conversation handler for this workflow.',

      'Reins receives the documented WeCom bot/group ticket notification text produced by the VPS wechat_kf system.',
      'The expected text block starts with `[WeChat Customer-Service Ticket]` and includes ticket_id, category, priority, resident_ref, summary, source, and created_at.',
      "The Hermes WeCom gateway / WeCom reader should parse that text into JSON, then internally call `reins wecom work-order add --payload-json '{...}' --notify --json`.",
      'The web endpoint `POST /api/reins/wecom/work-orders` also accepts the raw text as `{ "message": "...", "notify": true }` and performs that parse/call step.',
      'Use ticket_id/external_id as the idempotency key. Repeated ticket notifications must update the same local record and must not create duplicate Excel rows.',
      'Notify the assigned responsible role only after the local Excel-backed record write succeeds.',
      'Responsible-role notification uses configured Enterprise WeChat webhook/API environment variables such as REINS_WECOM_NOTIFY_WEBHOOK_PROPERTY, REINS_WECOM_NOTIFY_WEBHOOK_CLEANING, REINS_WECOM_NOTIFY_WEBHOOK_POLICE, REINS_WECOM_NOTIFY_WEBHOOK_HOSPITAL, REINS_WECOM_NOTIFY_WEBHOOK_COMMUNITY, or REINS_WECOM_NOTIFY_WEBHOOK_DEFAULT.',

      "For staff follow-up replies, use `reins wecom work-order reply --payload-json '{...}' --json` or POST `/api/reins/wecom/work-orders/replies`.",
      'A staff reply must update the existing ticket by external_id/ticket_id instead of creating a new ticket.',
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

    transport:
      'Structured work-order payload from VPS wechat_kf or temporary Enterprise WeChat bridge',

    preferred_processor_commands: [
      'reins wecom doctor --json',
      "reins wecom work-order add --payload-json '{...}' --notify --json",
      'reins wecom work-order add --message "<WeCom ticket text>" --notify --json',
      "reins wecom work-order reply --payload-json '{...}' --json",
      'reins wecom work-order reply --external-id "<ticket_id>" --message "<staff reply>" --json',
      'reins wecom records export --json',
      'reins wecom records report --kind work_order --json',
    ],

    preferred_http_endpoints: [
      'POST /api/reins/wecom/work-orders',
      'POST /api/reins/wecom/work-orders/replies',
    ],

    decision_flow: [
      'Receive documented WeCom ticket notification text from VPS wechat_kf.',
      'Parse that text into JSON fields.',
      'Validate required fields, especially ticket_id/external_id.',
      'Use ticket_id/external_id as the idempotency key.',
      'Create or update the same local ticket record.',
      'Classify the ticket and assign the responsible role.',
      'Write or update the Excel-backed ledger.',
      'Notify the responsible staff target only after the local record write succeeds.',
      'When staff reply, update the same ticket row and append progress/resolution information.',
      'Generate progress or closure report.',
      'If data is malformed or uncertain, mark waiting_human_review and notify a human-review/default target.',
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
