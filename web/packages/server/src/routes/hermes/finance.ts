import Router from '@koa/router'
import {
  exportFinanceTransactions,
  getFinanceSummary,
  listFinanceTransactions,
  parseFinanceQuery,
} from '../../services/hermes/finance'

export const financeRoutes = new Router()

function handleError(ctx: any, err: any) {
  const message = err?.message || 'Finance request failed'
  const isBadRequest = /invalid|limit|offset|start date|month/i.test(message)
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

financeRoutes.post('/api/hermes/finance/export', async (ctx) => {
  try {
    const body = ctx.request.body as Record<string, unknown> | undefined
    const query = parseFinanceQuery(body || {})
    ctx.body = await exportFinanceTransactions(query)
  } catch (err: any) {
    handleError(ctx, err)
  }
})
