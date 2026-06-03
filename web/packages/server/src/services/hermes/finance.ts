import { existsSync } from 'fs';
import { mkdir, writeFile } from 'fs/promises';
import { basename, dirname, join, resolve } from 'path';
import { homedir } from 'os';
import { DatabaseSync } from 'node:sqlite';

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

const CSV_COLUMNS = [
  'id',
  'type',
  'amount',
  'currency',
  'category',
  'description',
  'counterparty',
  'payment_method',
  'occurred_at',
  'created_at',
  'updated_at',
  // 'source',
  'status',
];

type SqlParam = string | number | null;

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

export function getFinanceHome(): string {
  return join(getReinsHome(), 'finance');
}

export function getFinanceDbPath(): string {
  return join(getFinanceHome(), 'finance.sqlite');
}

function openFinanceDb(): DatabaseSync | null {
  const dbPath = getFinanceDbPath();
  if (!existsSync(dbPath)) return null;

  const db = new DatabaseSync(dbPath, {
    readOnly: true,
    timeout: 5000,
  });
  db.exec('PRAGMA query_only = ON');
  db.exec('PRAGMA busy_timeout = 5000');
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
    CSV_COLUMNS.join(','),
    ...transactions.map((tx) =>
      CSV_COLUMNS.map((column) => csvEscape((tx as any)[column])).join(','),
    ),
  ];
  return `\uFEFF${lines.join('\n')}\n`;
}

export async function exportFinanceTransactions(
  query: FinanceQuery,
): Promise<{ path: string; fileName: string; count: number }> {
  const exportDir = join(getFinanceHome(), 'export');
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
