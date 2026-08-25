import { existsSync, mkdirSync } from 'fs';
import { mkdir, writeFile } from 'fs/promises';
import { join } from 'path';
import { DatabaseSync } from 'node:sqlite';
import { resolveReinsHome } from './reins-path';
import { reinsWorkspaceDir } from '../reins/workspace-path';

export type FinanceTransactionType = 'income' | 'expense';

export interface FinanceTransaction {
  id: number;
  type: FinanceTransactionType;
  amount: number;
  currency: string;
  category: string;
  description: string;
  counterparty: string | null;
  payment_method: string | null;
  occurred_at: string;
  created_at: string;
  updated_at: string | null;
  source: string;
  status: string;
}

export interface FinanceTransactionPayload {
  type: FinanceTransactionType;
  amount: number;
  currency?: string | null;
  category?: string | null;
  description: string;
  counterparty?: string | null;
  payment_method?: string | null;
  occurred_at: string;
}

export interface FinanceQuery {
  startDate?: string | null;
  endDate?: string | null;
  type?: FinanceTransactionType | null;
  category?: string | null;
  limit?: number;
  offset?: number;
}

export interface FinanceCategoryTotal {
  category: string;
  amount: number;
}

export interface FinanceSummary {
  financeHome: string;
  databasePath: string;
  databaseExists: boolean;
  start_date: string;
  end_date: string;
  total_income: number;
  total_expense: number;
  net: number;
  transaction_count: number;
  income_by_category: FinanceCategoryTotal[];
  expense_by_category: FinanceCategoryTotal[];
  recent_transactions: FinanceTransaction[];
}

const CSV_COLUMNS: Array<{
  header: string;
  value: (transaction: FinanceTransaction) => unknown;
}> = [
  { header: 'ID/编号', value: (tx) => tx.id },
  { header: 'Type/类型', value: (tx) => tx.type },
  { header: 'Amount/金额', value: (tx) => tx.amount },
  { header: 'Currency/币种', value: (tx) => tx.currency },
  { header: 'Category/分类', value: (tx) => tx.category },
  { header: 'Description/描述', value: (tx) => tx.description },
  { header: 'Counterparty/交易对象', value: (tx) => tx.counterparty },
  { header: 'Payment Method/支付方式', value: (tx) => tx.payment_method },
  {
    header: 'Transaction Date/交易日期',
    value: (tx) => formatCsvDate(tx.occurred_at),
  },
  { header: 'Created At/创建时间', value: (tx) => formatCsvDateTime(tx.created_at) },
  { header: 'Updated At/更新时间', value: (tx) => formatCsvDateTime(tx.updated_at) },
];

type SqlParam = string | number | null;

const FINANCE_SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS finance_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
  amount REAL NOT NULL CHECK (amount > 0),
  currency TEXT NOT NULL DEFAULT 'CNY',
  category TEXT NOT NULL DEFAULT '其他',
  description TEXT NOT NULL,
  counterparty TEXT,
  payment_method TEXT,
  occurred_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  raw_text TEXT,
  status TEXT NOT NULL DEFAULT 'posted' CHECK (status IN ('posted', 'voided'))
);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_occurred_at
ON finance_transactions (occurred_at);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_type
ON finance_transactions (type);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_category
ON finance_transactions (category);

CREATE INDEX IF NOT EXISTS idx_finance_transactions_status
ON finance_transactions (status);

CREATE TABLE IF NOT EXISTS finance_schema_migrations (
  id TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

INSERT OR IGNORE INTO finance_schema_migrations (id, applied_at)
VALUES ('001_init.sql', datetime('now'));
`;

export function getReinsHome(): string {
  return resolveReinsHome();
}

export function getFinanceHome(): string {
  return join(getReinsHome(), 'finance');
}

export function getFinanceDbPath(): string {
  return join(getFinanceHome(), 'finance.sqlite');
}

function ensureFinanceDirectoriesSync(): void {
  const financeHome = getFinanceHome();
  mkdirSync(financeHome, { recursive: true });
  mkdirSync(join(financeHome, 'export'), { recursive: true });
  mkdirSync(join(financeHome, 'backups'), { recursive: true });
}

function ensureFinanceSchema(db: DatabaseSync): void {
  db.exec(FINANCE_SCHEMA_SQL);
}

function openFinanceDb(readOnly = true): DatabaseSync | null {
  const dbPath = getFinanceDbPath();
  if (!existsSync(dbPath)) {
    if (readOnly) return null;
    ensureFinanceDirectoriesSync();
  }

  const db = new DatabaseSync(dbPath, {
    readOnly,
    timeout: 5000,
  });
  db.exec('PRAGMA busy_timeout = 5000');
  db.exec('PRAGMA foreign_keys = ON');
  if (readOnly) {
    db.exec('PRAGMA query_only = ON');
  } else {
    db.exec('PRAGMA journal_mode = WAL');
    ensureFinanceSchema(db);
  }
  return db;
}

function toIsoDate(value: unknown, fallback: string): string {
  const raw = String(value || '').trim();
  if (!raw) return fallback;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    throw new Error('Invalid date format. Use YYYY-MM-DD.');
  }
  const [year, month, day] = raw.split('-').map(Number);
  const parsed = new Date(year, month - 1, day);
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    throw new Error('Invalid date value.');
  }
  return raw;
}

function currentMonthRange(now = new Date()): {
  startDate: string;
  endDate: string;
} {
  const year = now.getFullYear();
  const month = now.getMonth();
  const start = new Date(year, month, 1);
  const end = new Date(year, month + 1, 0);
  return {
    startDate: formatDate(start),
    endDate: formatDate(end),
  };
}

function monthRange(month: string): { startDate: string; endDate: string } {
  const match = /^(\d{4})-(\d{2})$/.exec(month.trim());
  if (!match) throw new Error('Invalid month format. Use YYYY-MM.');

  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  if (monthIndex < 0 || monthIndex > 11)
    throw new Error('Month must be between 01 and 12.');

  return {
    startDate: formatDate(new Date(year, monthIndex, 1)),
    endDate: formatDate(new Date(year, monthIndex + 1, 0)),
  };
}

function formatDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatCsvDate(value: string | null | undefined): string {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;

  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return formatDate(parsed);
}

function formatCsvDateTime(value: string | null | undefined): string {
  const raw = String(value || '').trim();
  if (!raw) return '';

  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;

  const hours = String(parsed.getHours()).padStart(2, '0');
  const minutes = String(parsed.getMinutes()).padStart(2, '0');
  const seconds = String(parsed.getSeconds()).padStart(2, '0');
  return `${formatDate(parsed)} ${hours}:${minutes}:${seconds}`;
}

export function resolveFinancePeriod(query: Record<string, unknown>): {
  startDate: string;
  endDate: string;
} {
  if (typeof query.month === 'string' && query.month.trim()) {
    return monthRange(query.month);
  }

  const current = currentMonthRange();
  const startDate = toIsoDate(query.start_date, current.startDate);
  const endDate = toIsoDate(query.end_date, current.endDate);
  if (startDate > endDate)
    throw new Error('Start date cannot be later than end date.');
  return { startDate, endDate };
}

function parseTransactionType(value: unknown): FinanceTransactionType | null {
  if (value === 'income' || value === 'expense') return value;
  if (value == null || value === '') return null;
  throw new Error('Invalid transaction type.');
}

function parseRequiredTransactionType(value: unknown): FinanceTransactionType {
  const parsed = parseTransactionType(value);
  if (!parsed) throw new Error('Transaction type is required.');
  return parsed;
}

function parseLimit(value: unknown, fallback: number, max: number): number {
  if (value == null || value === '') return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0)
    throw new Error('Limit must be a positive integer.');
  return Math.min(parsed, max);
}

function parseOffset(value: unknown): number {
  if (value == null || value === '') return 0;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0)
    throw new Error('Offset cannot be negative.');
  return parsed;
}

function parseTransactionId(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error('Invalid transaction id.');
  }
  return parsed;
}

function parseRequiredDate(value: unknown): string {
  const raw = String(value || '').trim();
  if (!raw) throw new Error('Transaction date is required.');
  return toIsoDate(raw, '');
}

function parseAmount(value: unknown): number {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) {
    throw new Error('Amount must be greater than zero.');
  }
  return amount;
}

function parseRequiredText(value: unknown, field: string): string {
  const text = String(value || '').trim();
  if (!text) throw new Error(`${field} is required.`);
  return text;
}

function parseOptionalText(value: unknown): string | null {
  const text = String(value || '').trim();
  return text ? text : null;
}

function parseFinanceTransactionPayload(
  body: Record<string, unknown>,
): FinanceTransactionPayload {
  const type = parseRequiredTransactionType(body.type);
  const currency =
    String(body.currency || 'CNY')
      .trim()
      .toUpperCase() || 'CNY';
  if (!/^[A-Z]{3,8}$/.test(currency)) throw new Error('Invalid currency.');

  return {
    type,
    amount: parseAmount(body.amount),
    currency,
    category: parseRequiredText(body.category || '其他', 'Category'),
    description: parseRequiredText(body.description, 'Description'),
    counterparty: parseOptionalText(body.counterparty),
    payment_method: parseOptionalText(body.payment_method),
    occurred_at: parseRequiredDate(body.occurred_at),
  };
}

export function parseFinanceQuery(
  query: Record<string, unknown>,
): FinanceQuery {
  const period = resolveFinancePeriod(query);
  return {
    ...period,
    type: parseTransactionType(query.type),
    category:
      typeof query.category === 'string' && query.category.trim()
        ? query.category.trim()
        : null,
    limit: parseLimit(query.limit, 50, 500),
    offset: parseOffset(query.offset),
  };
}

function rowToTransaction(row: Record<string, unknown>): FinanceTransaction {
  return {
    id: Number(row.id),
    type: row.type === 'income' ? 'income' : 'expense',
    amount: Number(row.amount || 0),
    currency: String(row.currency || 'CNY'),
    category: String(row.category || '其他'),
    description: String(row.description || ''),
    counterparty: row.counterparty == null ? null : String(row.counterparty),
    payment_method:
      row.payment_method == null ? null : String(row.payment_method),
    occurred_at: String(row.occurred_at || ''),
    created_at: String(row.created_at || ''),
    updated_at: row.updated_at == null ? null : String(row.updated_at),
    source: String(row.source || 'manual'),
    status: String(row.status || 'posted'),
  };
}

function buildWhere(
  query: FinanceQuery,
  includeVoided = false,
): { sql: string; params: SqlParam[] } {
  const clauses = [];
  const params: SqlParam[] = [];

  if (!includeVoided) {
    clauses.push('status = ?');
    params.push('posted');
  }
  if (query.startDate) {
    clauses.push('occurred_at >= ?');
    params.push(query.startDate);
  }
  if (query.endDate) {
    clauses.push('occurred_at <= ?');
    params.push(query.endDate);
  }
  if (query.type) {
    clauses.push('type = ?');
    params.push(query.type);
  }
  if (query.category) {
    clauses.push('category = ?');
    params.push(query.category);
  }

  return {
    sql: clauses.length ? `WHERE ${clauses.join(' AND ')}` : '',
    params,
  };
}

function listFinanceTransactionsFromDb(
  db: DatabaseSync,
  query: FinanceQuery,
): FinanceTransaction[] {
  const where = buildWhere(query);
  const rows = db
    .prepare(
      `
      SELECT id, type, amount, currency, category, description, counterparty,
             payment_method, occurred_at, created_at, updated_at, source, status
      FROM finance_transactions
      ${where.sql}
      ORDER BY occurred_at DESC, id DESC
      LIMIT ?
      OFFSET ?
    `,
    )
    .all(...where.params, query.limit ?? 50, query.offset ?? 0) as Record<
    string,
    unknown
  >[];

  return rows.map(rowToTransaction);
}

function getFinanceTransactionByIdFromDb(
  db: DatabaseSync,
  id: number,
): FinanceTransaction {
  const row = db
    .prepare(
      `
    SELECT id, type, amount, currency, category, description, counterparty,
           payment_method, occurred_at, created_at, updated_at, source, status
    FROM finance_transactions
    WHERE id = ?
  `,
    )
    .get(id) as Record<string, unknown> | undefined;

  if (!row) throw new Error('Transaction not found.');
  return rowToTransaction(row);
}

export function listFinanceTransactions(
  query: FinanceQuery,
): FinanceTransaction[] {
  const db = openFinanceDb();
  if (!db) return [];

  try {
    return listFinanceTransactionsFromDb(db, query);
  } finally {
    db.close();
  }
}

export function createFinanceTransaction(
  body: Record<string, unknown>,
): FinanceTransaction {
  const payload = parseFinanceTransactionPayload(body);
  const db = openFinanceDb(false);
  if (!db) throw new Error('Finance database could not be opened.');

  try {
    const createdAt = new Date().toISOString();
    const result = db
      .prepare(
        `
      INSERT INTO finance_transactions (
        type, amount, currency, category, description, counterparty,
        payment_method, occurred_at, created_at, updated_at, source, raw_text, status
      )
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'manual', NULL, 'posted')
    `,
      )
      .run(
        payload.type,
        payload.amount,
        payload.currency || 'CNY',
        payload.category || '其他',
        payload.description,
        payload.counterparty ?? null,
        payload.payment_method ?? null,
        payload.occurred_at,
        createdAt,
      ) as { lastInsertRowid?: number | bigint };

    return getFinanceTransactionByIdFromDb(db, Number(result.lastInsertRowid));
  } finally {
    db.close();
  }
}

export function updateFinanceTransaction(
  idValue: unknown,
  body: Record<string, unknown>,
): FinanceTransaction {
  const id = parseTransactionId(idValue);
  const payload = parseFinanceTransactionPayload(body);
  const db = openFinanceDb(false);
  if (!db) throw new Error('Finance database could not be opened.');

  try {
    const updatedAt = new Date().toISOString();
    const result = db
      .prepare(
        `
      UPDATE finance_transactions
      SET type = ?,
          amount = ?,
          currency = ?,
          category = ?,
          description = ?,
          counterparty = ?,
          payment_method = ?,
          occurred_at = ?,
          updated_at = ?
      WHERE id = ?
    `,
      )
      .run(
        payload.type,
        payload.amount,
        payload.currency || 'CNY',
        payload.category || '其他',
        payload.description,
        payload.counterparty ?? null,
        payload.payment_method ?? null,
        payload.occurred_at,
        updatedAt,
        id,
      ) as { changes?: number | bigint };

    if (Number(result.changes || 0) === 0) {
      throw new Error('Transaction not found.');
    }

    return getFinanceTransactionByIdFromDb(db, id);
  } finally {
    db.close();
  }
}

export function deleteFinanceTransaction(idValue: unknown): FinanceTransaction {
  const id = parseTransactionId(idValue);
  const db = openFinanceDb(false);
  if (!db) throw new Error('Finance database could not be opened.');

  try {
    getFinanceTransactionByIdFromDb(db, id);
    const updatedAt = new Date().toISOString();
    db.prepare(
      `
      UPDATE finance_transactions
      SET status = 'voided',
          updated_at = ?
      WHERE id = ?
    `,
    ).run(updatedAt, id);

    return getFinanceTransactionByIdFromDb(db, id);
  } finally {
    db.close();
  }
}

function categoryTotals(
  db: DatabaseSync,
  query: FinanceQuery,
  type: FinanceTransactionType,
): FinanceCategoryTotal[] {
  const where = buildWhere({ ...query, type });
  const rows = db
    .prepare(
      `
    SELECT category, COALESCE(SUM(amount), 0) AS amount
    FROM finance_transactions
    ${where.sql}
    GROUP BY category
    ORDER BY amount DESC, category ASC
  `,
    )
    .all(...where.params) as Record<string, unknown>[];

  return rows.map((row) => ({
    category: String(row.category || '其他'),
    amount: Number(row.amount || 0),
  }));
}

export function getFinanceSummary(query: FinanceQuery): FinanceSummary {
  const financeHome = getFinanceHome();
  const databasePath = getFinanceDbPath();
  const db = openFinanceDb();

  if (!db) {
    return {
      financeHome,
      databasePath,
      databaseExists: false,
      start_date: query.startDate || '',
      end_date: query.endDate || '',
      total_income: 0,
      total_expense: 0,
      net: 0,
      transaction_count: 0,
      income_by_category: [],
      expense_by_category: [],
      recent_transactions: [],
    };
  }

  try {
    const where = buildWhere(query);
    const totals = db
      .prepare(
        `
      SELECT
        COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS total_income,
        COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS total_expense,
        COUNT(*) AS transaction_count
      FROM finance_transactions
      ${where.sql}
    `,
      )
      .get(...where.params) as Record<string, unknown>;

    const recent = listFinanceTransactionsFromDb(db, {
      ...query,
      limit: 4,
      offset: 0,
    });
    const totalIncome = Number(totals.total_income || 0);
    const totalExpense = Number(totals.total_expense || 0);

    return {
      financeHome,
      databasePath,
      databaseExists: true,
      start_date: query.startDate || '',
      end_date: query.endDate || '',
      total_income: totalIncome,
      total_expense: totalExpense,
      net: totalIncome - totalExpense,
      transaction_count: Number(totals.transaction_count || 0),
      income_by_category: categoryTotals(db, query, 'income'),
      expense_by_category: categoryTotals(db, query, 'expense'),
      recent_transactions: recent,
    };
  } finally {
    db.close();
  }
}

function csvEscape(value: unknown): string {
  const raw = value == null ? '' : String(value);
  if (!/[",\r\n]/.test(raw)) return raw;
  return `"${raw.replace(/"/g, '""')}"`;
}

function transactionsToCsv(transactions: FinanceTransaction[]): string {
  const lines = [
    CSV_COLUMNS.map((column) => csvEscape(column.header)).join(','),
    ...transactions.map((tx) =>
      CSV_COLUMNS.map((column) => csvEscape(column.value(tx))).join(','),
    ),
  ];
  return `\uFEFF${lines.join('\n')}\n`;
}

export async function exportFinanceTransactions(
  query: FinanceQuery,
): Promise<{ path: string; fileName: string; count: number }> {
  const exportDir = join(reinsWorkspaceDir('Generated'), 'Finance');
  await mkdir(exportDir, { recursive: true });

  const transactions = listFinanceTransactions({
    ...query,
    limit: 100_000,
    offset: 0,
  });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const fileName = `reins-finance-${query.startDate || 'all'}-to-${query.endDate || 'all'}-${stamp}.csv`;
  const outputPath = join(exportDir, fileName);
  await writeFile(outputPath, transactionsToCsv(transactions), 'utf-8');

  return { path: outputPath, fileName, count: transactions.length };
}
