import Router from '@koa/router'
import { readFile } from 'fs/promises'
import {
  createOfficeDocument,
  getOfficePreviewPath,
  getOfficeStatus,
  listOfficeDocuments,
  normalizeOfficeCreateRequest,
  normalizeOfficeRevisionRequest,
  reviseOfficeDocument,
} from '../../services/reins/office'

export const officeRoutes = new Router()

function handleError(ctx: any, err: any) {
  const code = String(err?.code || 'internal_error')
  const statusByCode: Record<string, number> = {
    invalid_request: 400,
    not_found: 404,
    worker_timeout: 504,
    worker_error: 503,
    internal_error: 500,
  }
  ctx.status = statusByCode[code] || 500
  ctx.body = {
    error: err?.message || 'Office request failed.',
    code,
  }
}

officeRoutes.get('/api/reins/office/status', async ctx => {
  try {
    ctx.body = await getOfficeStatus()
  } catch (err) {
    handleError(ctx, err)
  }
})

officeRoutes.get('/api/reins/office/documents', async ctx => {
  try {
    ctx.body = { documents: await listOfficeDocuments(ctx.query.limit) }
  } catch (err) {
    handleError(ctx, err)
  }
})

officeRoutes.post('/api/reins/office/documents', async ctx => {
  try {
    const input = normalizeOfficeCreateRequest(ctx.request.body)
    ctx.status = 201
    ctx.body = { document: await createOfficeDocument(input) }
  } catch (err) {
    handleError(ctx, err)
  }
})

officeRoutes.post('/api/reins/office/documents/:id/revisions', async ctx => {
  try {
    const input = normalizeOfficeRevisionRequest(ctx.request.body)
    ctx.body = { document: await reviseOfficeDocument(ctx.params.id, input) }
  } catch (err) {
    handleError(ctx, err)
  }
})

officeRoutes.get('/api/reins/office/documents/:id/preview', async ctx => {
  try {
    const previewPath = await getOfficePreviewPath(ctx.params.id)
    const html = await readFile(previewPath, 'utf8')
    ctx.set('Content-Type', 'text/html; charset=utf-8')
    ctx.set('Cache-Control', 'no-store')
    ctx.set('Referrer-Policy', 'no-referrer')
    ctx.set(
      'Content-Security-Policy',
      "default-src 'none'; img-src data: blob:; style-src 'unsafe-inline' https://d.officecli.ai https://fonts.googleapis.com https://cdn.jsdelivr.net; script-src 'unsafe-inline' https://d.officecli.ai https://cdn.jsdelivr.net; font-src data: https://d.officecli.ai https://fonts.gstatic.com; connect-src 'none'; base-uri 'none'; frame-ancestors 'self'",
    )
    ctx.body = html
  } catch (err) {
    handleError(ctx, err)
  }
})
