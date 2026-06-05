import Router from '@koa/router'
import {
  createFinanceTransaction,
  deleteFinanceTransaction,
  exportFinanceTransactions,
  getFinanceSummary,
  listFinanceTransactions,
  parseFinanceQuery,
  updateFinanceTransaction,
} from '../../services/hermes/finance'

export const financeRoutes = new Router()

function handleError(ctx: any, err: any) {
  const message = err?.message || 'Finance request failed'
  if (/not found/i.test(message)) {
    ctx.status = 404
    ctx.body = { error: message }
    return
  }

  const isBadRequest = /invalid|required|limit|offset|start date|month|amount|currency|category|description|transaction date|transaction type/i.test(message)
  ctx.status = isBadRequest ? 400 : 500
  ctx.body = { error: message }
}

financeRoutes.get('/api/hermes/finance/summary', async (ctx) => {
  try {
    const query = parseFinanceQuery(ctx.query as Record<string, unknown>)
    ctx.body = getFinanceSummary(query)
  } catch (err: any) {
    handleError(ctx, err)
  }
})

financeRoutes.get('/api/hermes/finance/transactions', async (ctx) => {
  try {
    const query = parseFinanceQuery(ctx.query as Record<string, unknown>)
    ctx.body = {
      transactions: listFinanceTransactions(query),
      start_date: query.startDate,
      end_date: query.endDate,
      limit: query.limit,
      offset: query.offset,
    }
  } catch (err: any) {
    handleError(ctx, err)
  }
})

financeRoutes.post('/api/hermes/finance/transactions', async (ctx) => {
  try {
    const body = ctx.request.body as Record<string, unknown> | undefined
    ctx.body = { transaction: createFinanceTransaction(body || {}) }
  } catch (err: any) {
    handleError(ctx, err)
  }
})

financeRoutes.put('/api/hermes/finance/transactions/:id', async (ctx) => {
  try {
    const body = ctx.request.body as Record<string, unknown> | undefined
    ctx.body = { transaction: updateFinanceTransaction(ctx.params.id, body || {}) }
  } catch (err: any) {
    handleError(ctx, err)
  }
})

financeRoutes.delete('/api/hermes/finance/transactions/:id', async (ctx) => {
  try {
    ctx.body = { transaction: deleteFinanceTransaction(ctx.params.id) }
  } catch (err: any) {
    handleError(ctx, err)
  }
})

financeRoutes.post('/api/hermes/finance/export', async (ctx) => {
  try {
    const body = ctx.request.body as Record<string, unknown> | undefined
    const query = parseFinanceQuery(body || {})
    ctx.body = await exportFinanceTransactions(query)
  } catch (err: any) {
    handleError(ctx, err)
  }
})
