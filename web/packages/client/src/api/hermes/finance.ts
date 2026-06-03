import { request } from '../client'

export type FinanceTransactionType = 'income' | 'expense'

export interface FinanceTransaction {
  id: number
  type: FinanceTransactionType
  amount: number
  currency: string
  category: string
  description: string
  counterparty: string | null
  payment_method: string | null
  occurred_at: string
  created_at: string
  updated_at: string | null
  source: string
  status: string
}

export interface FinanceCategoryTotal {
  category: string
  amount: number
}

export interface FinanceSummary {
  financeHome: string
  databasePath: string
  databaseExists: boolean
  start_date: string
  end_date: string
  total_income: number
  total_expense: number
  net: number
  transaction_count: number
  income_by_category: FinanceCategoryTotal[]
  expense_by_category: FinanceCategoryTotal[]
  recent_transactions: FinanceTransaction[]
}

export interface FinanceTransactionsResponse {
  transactions: FinanceTransaction[]
  start_date: string
  end_date: string
  limit: number
  offset: number
}

export interface FinanceExportResponse {
  path: string
  fileName: string
  count: number
}

export interface FinanceQueryParams {
  start_date?: string
  end_date?: string
  month?: string
  type?: FinanceTransactionType | ''
  category?: string
  limit?: number
  offset?: number
}

function toSearchParams(params: FinanceQueryParams): URLSearchParams {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    search.set(key, String(value))
  })
  return search
}

export async function fetchFinanceSummary(params: FinanceQueryParams = {}): Promise<FinanceSummary> {
  const search = toSearchParams(params)
  return request<FinanceSummary>(`/api/hermes/finance/summary?${search.toString()}`)
}

export async function fetchFinanceTransactions(params: FinanceQueryParams = {}): Promise<FinanceTransactionsResponse> {
  const search = toSearchParams(params)
  return request<FinanceTransactionsResponse>(`/api/hermes/finance/transactions?${search.toString()}`)
}

export async function exportFinanceData(params: FinanceQueryParams = {}): Promise<FinanceExportResponse> {
  return request<FinanceExportResponse>('/api/hermes/finance/export', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}
