import Router from '@koa/router'
import {
  approveWorkModeConfirmation,
  getWorkModeCase,
  getWorkModeMedia,
  listWorkModeCases,
  normalizeWorkModeRunRequest,
  rejectWorkModeConfirmation,
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

workModeRoutes.get('/api/hermes/workmode/cases', async (ctx) => {
  try {
    const limit = Number(ctx.query.limit || 25)
    ctx.body = await listWorkModeCases(limit)
  } catch (err: any) {
    handleError(ctx, err)
  }
})

workModeRoutes.get('/api/hermes/workmode/cases/:caseId', async (ctx) => {
  try {
    const replay = await getWorkModeCase(ctx.params.caseId)
    if (!replay.ok) {
      ctx.status = replay.error === 'case_not_found' ? 404 : 500
    }
    ctx.body = replay
  } catch (err: any) {
    handleError(ctx, err)
  }
})

workModeRoutes.get('/api/hermes/workmode/media', async (ctx) => {
  try {
    const media = await getWorkModeMedia(String(ctx.query.path || ''))
    const encodedFileName = encodeURIComponent(media.fileName)

    ctx.set('Content-Type', media.mime)
    ctx.set('Content-Length', String(media.size))
    ctx.set('Content-Disposition', `inline; filename="${encodedFileName}"; filename*=UTF-8''${encodedFileName}`)
    ctx.set('Cache-Control', 'private, max-age=60')

    if (media.mime.startsWith('text/html')) {
      ctx.set('Content-Security-Policy', "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline';")
    }

    ctx.body = media.data
  } catch (err: any) {
    const statusMap: Record<string, number> = {
      missing_path: 400,
      invalid_path: 400,
      not_found: 404,
      ENOENT: 404,
      file_too_large: 413,
    }
    ctx.status = statusMap[String(err?.code || '')] || 500
    ctx.body = {
      error: err?.message || 'WorkMode media request failed',
      code: err?.code || 'unknown',
    }
  }
})

workModeRoutes.post('/api/hermes/workmode/cases/:caseId/confirmations/:confirmationId/approve', async (ctx) => {
  try {
    const result = await approveWorkModeConfirmation(ctx.params.caseId, ctx.params.confirmationId)
    if (!result.ok) ctx.status = result.error === 'case_not_found' || result.error === 'confirmation_not_found' ? 404 : 409
    ctx.body = result
  } catch (err: any) {
    handleError(ctx, err)
  }
})

workModeRoutes.post('/api/hermes/workmode/cases/:caseId/confirmations/:confirmationId/reject', async (ctx) => {
  try {
    const body = ctx.request.body && typeof ctx.request.body === 'object' ? ctx.request.body as Record<string, unknown> : {}
    const result = await rejectWorkModeConfirmation(ctx.params.caseId, ctx.params.confirmationId, String(body.reason || ''))
    if (!result.ok) ctx.status = result.error === 'case_not_found' || result.error === 'confirmation_not_found' ? 404 : 409
    ctx.body = result
  } catch (err: any) {
    handleError(ctx, err)
  }
})
