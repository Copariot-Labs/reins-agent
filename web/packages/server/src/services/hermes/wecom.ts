import { execFile } from 'child_process';
import { promisify } from 'util';
import { resolveReinsHome as resolveDefaultReinsHome } from './reins-path';

const execFileAsync = promisify(execFile);

const DEFAULT_WECOM_TIMEOUT_MS = 30000;
const MAX_STDOUT_BUFFER = 4 * 1024 * 1024;

function resolveReinsBin(): string {
  return (
    process.env.REINS_BIN?.trim() || process.env.HERMES_BIN?.trim() || 'reins'
  );
}

function resolveReinsHome(): string {
  return resolveDefaultReinsHome();
}

function timeoutMs(): number {
  const raw = process.env.REINS_WECOM_WEB_TIMEOUT_MS;
  const value = raw ? Number(raw) : DEFAULT_WECOM_TIMEOUT_MS;
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_WECOM_TIMEOUT_MS;
}

function parseJsonOutput(stdout: unknown): any {
  const text = String(stdout || '').trim();

  if (!text) {
    throw new Error('Reins WeCom returned empty output');
  }

  try {
    return JSON.parse(text);
  } catch {
    // Some CLIs may print logs before/after JSON.
    // Try extracting the first full JSON object.
  }

  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');

  if (start < 0 || end <= start) {
    throw new Error('Reins WeCom returned invalid JSON');
  }

  return JSON.parse(text.slice(start, end + 1));
}

function stringArg(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function boolArg(value: unknown, defaultValue: boolean): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'y', 'on'].includes(normalized)) return true;
    if (['false', '0', 'no', 'n', 'off'].includes(normalized)) return false;
  }
  return defaultValue;
}

function getTicketId(body: Record<string, unknown>): string {
  return stringArg(
    body.external_id ??
      body.externalId ??
      body.ticket_id ??
      body.ticketId ??
      body.id,
  );
}

function getReplyMessage(body: Record<string, unknown>): string {
  return stringArg(
    body.message ??
      body.reply ??
      body.staff_reply ??
      body.staffReply ??
      body.content,
  );
}

function normalizeTicketLabel(value: string): string {
  return value
    .replace(/^[·•-]\s*/, '')
    .replace(/[\s:：]+/g, '')
    .trim()
    .toLowerCase();
}

const TICKET_TEXT_FIELD_ALIASES: Record<string, string[]> = {
  external_id: [
    'ticket_id',
    'ticketId',
    'external_id',
    'externalId',
    'work_order_id',
    'workOrderId',
    '工单编号',
    '工单号',
    '工单ID',
    '编号',
  ],
  category: ['category', 'type', '问题类型', '问题类别', '工单类型', '工单类别', '分类', '类别', '类型'],
  priority: ['priority', 'urgency', 'level', '优先级', '紧急程度', '等级'],
  resident_ref: [
    'resident_ref',
    'residentRef',
    'customer_ref',
    'customerRef',
    'user_ref',
    'userRef',
    '居民引用',
    '居民标识',
    '客户引用',
    '微信客户',
    '客户标识',
  ],
  title: ['summary', 'title', 'subject', '摘要', '标题', '主题', '工单标题', '问题/现象'],
  description: ['description', 'content', 'problem', 'request', '问题描述', '描述', '内容', '居民诉求', '诉求', '问题', '客户原话', '居民原话'],
  location: ['location', 'address', '位置', '地点', '地址', '小区', '楼栋', '房号'],
  source_channel: ['source', 'source_channel', 'sourceChannel', 'channel', '来源', '消息来源', '来源渠道', '渠道'],
  ticket_created_at: ['created_at', 'createdAt', 'ticket_created_at', 'ticketCreatedAt', '创建时间', '工单创建时间', '生成时间'],
  upstream_status: ['upstream_status', 'upstreamStatus', '工单状态', '处理状态', '状态'],
  customer_assessment: ['customer_assessment', 'customerAssessment', '客服研判', '客服判断', '网格员研判', '网格研判', '研判'],
  handling_requirements: ['handling_requirements', 'handlingRequirements', '处理要求', '办理要求'],
  people_involved: ['people_involved', 'peopleInvolved', '涉及人数', '涉及人员'],
  current_danger: ['current_danger', 'currentDanger', '当前危险', '是否危险'],
};

const SECTION_FIELDS: Record<string, string> = {
  新建工单: '',
  客户描述: '',
  客户诉求: '',
  居民诉求: '',
  已核实信息: '',
  已确认信息: '',
  客服研判: 'customer_assessment',
  客服判断: 'customer_assessment',
  网格员研判: 'customer_assessment',
  网格研判: 'customer_assessment',
  处理要求: 'handling_requirements',
  系统信息: '',
  工单结束: '',
};

function normalizeTicketSection(value: string): string {
  return normalizeTicketLabel(value)
    .replace(/^[【\[]/, '')
    .replace(/[】\]]$/, '');
}

export function parseWeComTicketText(message: string): Record<string, unknown> {
  const text = stringArg(message);
  if (!text) return {};
  if (text.startsWith('【Reins工单通知】')) return {};

  const reverseAliases = new Map<string, string>();
  for (const [field, aliases] of Object.entries(TICKET_TEXT_FIELD_ALIASES)) {
    for (const alias of aliases) {
      reverseAliases.set(normalizeTicketLabel(alias), field);
    }
  }

  const parsed: Record<string, unknown> = {};
  const sectionValues = new Map<string, string[]>();
  let currentSection = '';

  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim().replace(/^[·•-]\s*/, '').trim();
    if (!trimmed || /^\[.+\]$/.test(trimmed)) continue;

    const sectionField = SECTION_FIELDS[normalizeTicketSection(trimmed)];
    if (sectionField !== undefined) {
      currentSection = sectionField;
      if (sectionField && !sectionValues.has(sectionField)) {
        sectionValues.set(sectionField, []);
      }
      continue;
    }

    const match = trimmed.match(/^([^:：]{1,40})[:：]\s*(.+)$/);
    if (!match) {
      if (currentSection) {
        sectionValues.get(currentSection)?.push(trimmed);
      }
      continue;
    }

    const label = normalizeTicketLabel(match[1]);
    const field = reverseAliases.get(label);
    if (!field) {
      if (currentSection) {
        sectionValues.get(currentSection)?.push(trimmed);
      }
      continue;
    }

    const value = match[2].trim();
    if (field === 'category' && parsed.category && parsed.category !== value) {
      parsed.original_category ??= parsed.category;
    }
    parsed[field] = value;
  }

  for (const [field, values] of sectionValues.entries()) {
    const value = values.filter(Boolean).join('\n').trim();
    if (value) parsed[field] = value;
  }

  return parsed;
}

function normalizeWorkOrderPayload(body: Record<string, unknown>): Record<string, unknown> {
  const rawMessage = stringArg(
    body.message ??
      body.text ??
      body.raw_message ??
      body.rawMessage ??
      body.content,
  );
  const parsed = parseWeComTicketText(rawMessage);
  const payload: Record<string, unknown> = { ...parsed, ...body };

  if (rawMessage && Object.keys(parsed).length > 0) {
    const metadata = payload.metadata && typeof payload.metadata === 'object' && !Array.isArray(payload.metadata)
      ? payload.metadata as Record<string, unknown>
      : {};
    payload.metadata = {
      ...metadata,
      raw_wecom_message: rawMessage,
      source_format: 'wecom_text_ticket_notification',
    };
  }

  return payload;
}

function validateWorkOrderPayload(body: Record<string, unknown>): void {
  if (!body || Object.keys(body).length === 0) {
    throw new Error('work order payload is required');
  }

  const ticketId = getTicketId(body);

  if (!ticketId) {
    throw new Error('ticket_id or external_id is required');
  }
}

function validateWorkOrderReplyPayload(body: Record<string, unknown>): void {
  if (!body || Object.keys(body).length === 0) {
    throw new Error('work order reply payload is required');
  }

  const ticketId = getTicketId(body);
  const message = getReplyMessage(body);

  if (!ticketId) {
    throw new Error('ticket_id or external_id is required');
  }

  if (!message) {
    throw new Error('reply message is required');
  }
}

async function runReinsCommand(args: string[]): Promise<any> {
  const reinsHome = resolveReinsHome();

  const { stdout } = await execFileAsync(resolveReinsBin(), args, {
    env: {
      ...process.env,
      REINS_HOME: reinsHome,
      HERMES_HOME: process.env.HERMES_HOME?.trim() || reinsHome,
    },
    encoding: 'utf8',
    maxBuffer: MAX_STDOUT_BUFFER,
    timeout: timeoutMs(),
    windowsHide: true,
  });

  return parseJsonOutput(stdout);
}

/**
 * New project-plan behavior:
 *
 * VPS wechat_kf handles:
 * - WeChat Customer Service callback
 * - resident conversation
 * - FAQ / LLM customer-service reply
 * - structured ticket creation
 *
 * Reins handles:
 * - structured work-order intake
 * - idempotent local record by ticket_id/external_id
 * - Excel ledger update
 * - classification / assignment
 * - staff notification
 * - report generation
 */
export async function processWeComWorkOrder(
  body: Record<string, unknown>,
): Promise<any> {
  const normalizedBody = normalizeWorkOrderPayload(body);
  validateWorkOrderPayload(normalizedBody);

  const shouldNotify = boolArg(normalizedBody.notify, true);

  /**
   * Do not mutate the original body object.
   * If "notify" is only a transport hint for this web server, remove it
   * before sending payload into the Reins CLI.
   */
  const payload = { ...normalizedBody };
  delete payload.notify;

  const args = [
    'wecom',
    'work-order',
    'add',
    '--payload-json',
    JSON.stringify(payload),
  ];

  if (shouldNotify) {
    args.push('--notify');
  }

  args.push('--json');

  return runReinsCommand(args);
}

/**
 * Staff reply / progress update flow:
 *
 * Staff or another system posts a reply/update for an existing ticket.
 * Reins must update the same local ticket record using ticket_id/external_id.
 */
export async function processWeComWorkOrderReply(
  body: Record<string, unknown>,
): Promise<any> {
  validateWorkOrderReplyPayload(body);

  const args = [
    'wecom',
    'work-order',
    'reply',
    '--payload-json',
    JSON.stringify(body),
    '--json',
  ];

  return runReinsCommand(args);
}
