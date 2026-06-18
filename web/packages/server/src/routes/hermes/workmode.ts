import Router from '@koa/router'
import {
  normalizeWorkModeRunRequest,
  startWorkModeRun,
} from '../../services/hermes/workmode'

export const workModeRoutes = new Router()

function handleError(ctx: any, err: any) {
  const message = err?.message || 'Work mode request failed'
  const isBadRequest = /required|invalid|mode/i.test(message)
  ctx.status = isBadRequest ? 400 : 500
  ctx.body = { error: message }
}

workModeRoutes.post('/api/hermes/workmode/run', async (ctx) => {
  let run

  try {
    const input = normalizeWorkModeRunRequest(ctx.request.body)
    run = startWorkModeRun(input)
  } catch (err: any) {
    handleError(ctx, err)
    return
  }

  ctx.status = 200
  ctx.set('Content-Type', 'text/event-stream; charset=utf-8')
  ctx.set('Cache-Control', 'no-cache, no-transform')
  ctx.set('Connection', 'keep-alive')
  ctx.set('X-Accel-Buffering', 'no')

  ctx.req.on('close', run.cancel)
  ctx.body = run.stream
})
