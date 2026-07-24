import { existsSync, readFileSync, statSync } from 'fs';
import { homedir } from 'os';
import { basename, dirname, join, resolve } from 'path';
import { DatabaseSync } from 'node:sqlite';

export interface WorkOrderQuery {
  search: string;
  status: string;
  priority: string;
  role: string;
  category: string;
  notificationStatus: string;
  limit: number;
  offset: number;
}

export interface WorkOrderRecord {
  id: number;
  external_id: string;
  created_at: string;
  updated_at: string;
  status: string;
  priority: string;
  category: string;
  assigned_role: string;
  assigned_role_label: string;
  assignees: string[];
  location: string;
  title: string;
  issue: string;
  customer_assessment: string;
  handling_requirements: string;
  resident_contact: string;
  notification_status: string;
  notification_channel: string;
  notification_error: string;
  result: string;
  responder: string;
  source_channel: string;
  upstream_status: string;
  assignment_reason: string;
}

export interface WorkOrderFilterOptions {
  statuses: string[];
  priorities: string[];
  roles: Array<{ value: string; label: string }>;
  categories: string[];
  notification_statuses: string[];
}

export interface WorkOrderExportInfo {
  available: boolean;
  file_name: string;
  updated_at: string;
  visible_path: string;
}

export interface WorkOrderSummary {
  database_exists: boolean;
  total: number;
  pending: number;
  processing: number;
  urgent: number;
  notification_failed: number;
  completed: number;
  last_updated: string;
  filters: WorkOrderFilterOptions;
  export: WorkOrderExportInfo;
}

type SqlRow = Record<string, unknown>;
type Metadata = Record<string, unknown>;

const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;
const PENDING_STATUSES = new Set([
  'new',
  'open',
  'pending_notification',
  'waiting_human_review',
]);
const COMPLETED_STATUSES = new Set(['resolved', 'closed']);
const URGENT_PRIORITIES = new Set(['high', 'urgent', 'critical', 'emergency']);
const FAILED_NOTIFICATION_STATUSES = new Set(['failed', 'pending_configuration']);

function clean(value: unknown): string {
  return value == null ? '' : String(value).trim();
}

function firstNonEmpty(...values: unknown[]): string {
  for (const value of values) {
    const candidate = clean(value);
    if (candidate) return candidate;
  }
  return '';
}

function parseMetadata(value: unknown): Metadata {
  const raw = clean(value);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Metadata)
      : {};
  } catch {
    return {};
  }
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.map(clean).filter(Boolean))];
}

function staffSafeMessage(value: unknown): string {
  return clean(value)
    .split(/\r?\n/)
    .filter(
      (line) =>
        !/^\s*(?:[-·]\s*)?(?:居民标识|客户标识|微信客户)\s*[：:].*$/.test(
          line,
        ),
    )
    .join('\n')
    .trim();
}

function combineIssue(metadata: Metadata, row: SqlRow): string {
  const title = clean(metadata.title);
  const description = clean(metadata.description);
  if (description) {
    return title && !description.includes(title)
      ? `${title}\n${description}`
      : description;
  }
  return title || staffSafeMessage(row.message);
}

function rowToWorkOrder(row: SqlRow): WorkOrderRecord {
  const metadata = parseMetadata(row.metadata_json);
  const explicitAssignee = clean(metadata.assignee);
  const assignees = stringList(metadata.notification_recipients);
  if (explicitAssignee && !assignees.includes(explicitAssignee)) {
    assignees.unshift(explicitAssignee);
  }

  return {
    id: Number(row.id || 0),
    external_id: firstNonEmpty(
      metadata.external_id,
      metadata.ticket_id,
      metadata.api_ticket_id,
      row.id,
    ),
    created_at: firstNonEmpty(
      metadata.ticket_created_at,
      metadata.api_created_at,
      row.created_at,
    ),
    updated_at: firstNonEmpty(
      metadata.last_staff_reply_at,
      metadata.api_updated_at,
      metadata.notified_at,
      metadata.analyzed_at,
      row.created_at,
    ),
    status: clean(row.status),
    priority: clean(metadata.priority),
    category: clean(metadata.category),
    assigned_role: clean(metadata.assigned_role),
    assigned_role_label: firstNonEmpty(
      metadata.assigned_role_label,
      metadata.assigned_role,
    ),
    assignees,
    location: clean(metadata.location),
    title: clean(metadata.title),
    issue: combineIssue(metadata, row),
    customer_assessment: clean(metadata.customer_assessment),
    handling_requirements: clean(metadata.handling_requirements),
    resident_contact: clean(metadata.resident_contact),
    notification_status: clean(metadata.notification_status),
    notification_channel: clean(metadata.notification_channel),
    notification_error: clean(metadata.notification_error),
    result: firstNonEmpty(metadata.last_staff_reply, row.reply),
    responder: firstNonEmpty(
      metadata.last_staff_responder,
      metadata.assignee,
    ),
    source_channel: clean(metadata.source_channel),
    upstream_status: firstNonEmpty(
      metadata.upstream_status,
      metadata.api_status,
    ),
    assignment_reason: clean(metadata.assignment_reason),
  };
}

function resolveRootHomeFromHermes(value: string): string {
  const home = resolve(value);
  const parent = dirname(home);
  if (basename(parent) === 'profiles') return dirname(parent);
  return home;
}

export function getReinsHome(): string {
  const reinsHome = process.env.REINS_HOME?.trim();
  if (reinsHome) return resolve(reinsHome);

  const hermesHome = process.env.HERMES_HOME?.trim();
  if (hermesHome) return resolveRootHomeFromHermes(hermesHome);

  return join(homedir(), '.reins');
}

export function getWorkOrderDbPath(): string {
  return join(getReinsHome(), 'wecom', 'wecom.sqlite');
}

export function getWorkOrderWorkbookPath(): string {
  return join(getReinsHome(), 'wecom', 'records.xlsx');
}

function unquoteEnvValue(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function readReinsEnvValue(key: string): string {
  const inherited = process.env[key]?.trim();
  if (inherited) return unquoteEnvValue(inherited);

  try {
    const raw = readFileSync(join(getReinsHome(), '.env'), 'utf8');
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = raw.match(new RegExp(`^\\s*${escapedKey}\\s*=\\s*(.+?)\\s*$`, 'm'));
    return match ? unquoteEnvValue(match[1]) : '';
  } catch {
    return '';
  }
}

export function getVisibleWorkOrderWorkbookPath(): string {
  const configured = readReinsEnvValue('REINS_WECOM_EXPORT_DIR');
  if (!configured) return '';
  const directory = configured.startsWith('~/')
    ? join(homedir(), configured.slice(2))
    : resolve(configured);
  return join(directory, '社区工单台账.xlsx');
}

function openWorkOrderDb(): DatabaseSync | null {
  const path = getWorkOrderDbPath();
  if (!existsSync(path)) return null;

  const db = new DatabaseSync(path, {
    readOnly: true,
    timeout: 5000,
  });
  db.exec('PRAGMA busy_timeout = 5000');
  db.exec('PRAGMA query_only = ON');
  return db;
}

function readAllWorkOrders(): WorkOrderRecord[] {
  const db = openWorkOrderDb();
  if (!db) return [];

  try {
    const rows = db
      .prepare(
        `
        SELECT id, created_at, kind, status, message, reply, metadata_json
        FROM wecom_records
        WHERE kind = 'work_order'
        ORDER BY id DESC
      `,
      )
      .all() as SqlRow[];
    return rows.map(rowToWorkOrder);
  } finally {
    db.close();
  }
}

function parseLimit(value: unknown): number {
  if (value == null || value === '') return DEFAULT_LIMIT;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error('Limit must be a positive integer.');
  }
  return Math.min(parsed, MAX_LIMIT);
}

function parseOffset(value: unknown): number {
  if (value == null || value === '') return 0;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error('Offset must be a non-negative integer.');
  }
  return parsed;
}

export function parseWorkOrderQuery(
  query: Record<string, unknown>,
): WorkOrderQuery {
  return {
    search: clean(query.search),
    status: clean(query.status),
    priority: clean(query.priority),
    role: clean(query.role),
    category: clean(query.category),
    notificationStatus: clean(
      query.notification_status ?? query.notificationStatus,
    ),
    limit: parseLimit(query.limit),
    offset: parseOffset(query.offset),
  };
}

function matchesQuery(record: WorkOrderRecord, query: WorkOrderQuery): boolean {
  if (query.status && record.status !== query.status) return false;
  if (query.priority && record.priority !== query.priority) return false;
  if (query.role && record.assigned_role !== query.role) return false;
  if (query.category && record.category !== query.category) return false;
  if (
    query.notificationStatus &&
    record.notification_status !== query.notificationStatus
  ) {
    return false;
  }

  const search = query.search.toLocaleLowerCase();
  if (!search) return true;
  return [
    record.external_id,
    record.location,
    record.title,
    record.issue,
    record.category,
    record.assigned_role_label,
    record.assignees.join(' '),
    record.result,
  ].some((value) => value.toLocaleLowerCase().includes(search));
}

function uniqueSorted(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, 'zh-CN'),
  );
}

function filterOptions(records: WorkOrderRecord[]): WorkOrderFilterOptions {
  const roleLabels = new Map<string, string>();
  for (const record of records) {
    if (record.assigned_role) {
      roleLabels.set(
        record.assigned_role,
        record.assigned_role_label || record.assigned_role,
      );
    }
  }

  return {
    statuses: uniqueSorted(records.map((record) => record.status)),
    priorities: uniqueSorted(records.map((record) => record.priority)),
    roles: [...roleLabels.entries()]
      .map(([value, label]) => ({ value, label }))
      .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN')),
    categories: uniqueSorted(records.map((record) => record.category)),
    notification_statuses: uniqueSorted(
      records.map((record) => record.notification_status),
    ),
  };
}

export function getWorkOrderExportInfo(): WorkOrderExportInfo {
  const workbook = getWorkOrderWorkbookPath();
  const visiblePath = getVisibleWorkOrderWorkbookPath();
  const available = existsSync(workbook);
  const updatedAt = available
    ? statSync(workbook).mtime.toISOString()
    : '';

  return {
    available,
    file_name: '社区工单台账.xlsx',
    updated_at: updatedAt,
    visible_path: visiblePath,
  };
}

function summarize(records: WorkOrderRecord[]): WorkOrderSummary {
  return {
    database_exists: existsSync(getWorkOrderDbPath()),
    total: records.length,
    pending: records.filter((record) => PENDING_STATUSES.has(record.status))
      .length,
    processing: records.filter((record) => record.status === 'processing')
      .length,
    urgent: records.filter((record) =>
      URGENT_PRIORITIES.has(record.priority.toLocaleLowerCase()),
    ).length,
    notification_failed: records.filter((record) =>
      FAILED_NOTIFICATION_STATUSES.has(record.notification_status),
    ).length,
    completed: records.filter((record) =>
      COMPLETED_STATUSES.has(record.status),
    ).length,
    last_updated: records.reduce(
      (latest, record) =>
        record.updated_at > latest ? record.updated_at : latest,
      '',
    ),
    filters: filterOptions(records),
    export: getWorkOrderExportInfo(),
  };
}

export function getWorkOrderSummary(): WorkOrderSummary {
  return summarize(readAllWorkOrders());
}

export function listWorkOrders(query: WorkOrderQuery): {
  records: WorkOrderRecord[];
  total: number;
  limit: number;
  offset: number;
} {
  const matching = readAllWorkOrders().filter((record) =>
    matchesQuery(record, query),
  );
  return {
    records: matching.slice(query.offset, query.offset + query.limit),
    total: matching.length,
    limit: query.limit,
    offset: query.offset,
  };
}

export function getWorkOrderById(idValue: unknown): WorkOrderRecord {
  const id = Number(idValue);
  if (!Number.isInteger(id) || id <= 0) {
    throw new Error('Invalid work order id.');
  }

  const record = readAllWorkOrders().find((candidate) => candidate.id === id);
  if (!record) throw new Error('Work order not found.');
  return record;
}
