import Router from '@koa/router'

import {
  MAX_PRESENTATION_SOURCE_SIZE,
  createPresentationChat,
  createPresentationSession,
  getPresentationSession,
  getPresentationJob,
  getPresentationMedia,
  listPresentationSessions,
  listPresentationJobs,
  submitPresentationSessionTurn,
  submitPresentationJob,
} from '../../services/hermes/presentations'

export const presentationRoutes = new Router()

function handleError(ctx: any, error: any) {
  const code = String(error?.code || 'internal_error')
  const statusByCode: Record<string, number> = {
    invalid_request: 400,
    not_found: 404,
    not_ready: 409,
    conflict: 409,
    file_too_large: 413,
    invalid_state: 500,
    worker_error: 503,
  }
  ctx.status = statusByCode[code] || 500
  ctx.body = {
    error: error?.message || 'Presentation request failed.',
    code,
  }
}

function splitMultipart(raw: Buffer, boundary: Buffer): Buffer[] {
  const parts: Buffer[] = []
  let cursor = 0
  while (true) {
    const index = raw.indexOf(boundary, cursor)
    if (index === -1) break
    if (cursor > 0) parts.push(raw.subarray(cursor + 2, index))
    cursor = index + boundary.length
  }
  return parts
}

async function readPresentationUpload(ctx: any): Promise<{ fileName: string, data: Buffer }> {
  const contentType = String(ctx.get('content-type') || '')
  const boundaryMatch = contentType.match(/boundary=(?:"([^"]+)"|([^;]+))/i)
  const boundaryValue = boundaryMatch?.[1] || boundaryMatch?.[2]
  if (!contentType.startsWith('multipart/form-data') || !boundaryValue) {
    throw Object.assign(new Error('Expected a PPTX or PDF multipart upload.'), { code: 'invalid_request' })
  }

  const chunks: Buffer[] = []
  let total = 0
  for await (const chunk of ctx.req) {
    const value = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    total += value.length
    if (total > MAX_PRESENTATION_SOURCE_SIZE + 1024 * 1024) {
      throw Object.assign(new Error('The uploaded presentation source is too large.'), { code: 'file_too_large' })
    }
    chunks.push(value)
  }

  const raw = Buffer.concat(chunks)
  for (const part of splitMultipart(raw, Buffer.from(`--${boundaryValue}`))) {
    const headerEnd = part.indexOf(Buffer.from('\r\n\r\n'))
    if (headerEnd === -1) continue
    const header = part.subarray(0, headerEnd).toString('utf8')
    const encodedName = header.match(/filename\*=UTF-8''([^\r\n;]+)/i)?.[1]
    const plainName = header.match(/filename="([^"]+)"/i)?.[1]
    if (!encodedName && !plainName) continue
    const fileName = encodedName ? decodeURIComponent(encodedName) : String(plainName)
    return {
      fileName,
      data: part.subarray(headerEnd + 4, Math.max(headerEnd + 4, part.length - 2)),
    }
  }
  throw Object.assign(new Error('A PPTX or PDF file is required.'), { code: 'invalid_request' })
}

presentationRoutes.get('/api/hermes/presentation-sessions', async ctx => {
  try {
    ctx.body = { sessions: await listPresentationSessions(ctx.query.limit) }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.post('/api/hermes/presentation-sessions', async ctx => {
  try {
    const upload = await readPresentationUpload(ctx)
    ctx.status = 201
    ctx.body = { session: await createPresentationSession(upload.fileName, upload.data) }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.post('/api/hermes/presentation-sessions/create', async ctx => {
  try {
    ctx.status = 202
    ctx.body = { session: await createPresentationChat(ctx.request.body) }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.get('/api/hermes/presentation-sessions/:sessionId', async ctx => {
  try {
    ctx.body = { session: await getPresentationSession(ctx.params.sessionId) }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.post('/api/hermes/presentation-sessions/:sessionId/messages', async ctx => {
  try {
    ctx.status = 202
    ctx.body = {
      session: await submitPresentationSessionTurn(ctx.params.sessionId, ctx.request.body),
    }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.get('/api/hermes/presentations', async ctx => {
  try {
    ctx.body = { jobs: await listPresentationJobs(ctx.query.limit) }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.post('/api/hermes/presentations', async ctx => {
  try {
    ctx.status = 202
    ctx.body = { job: await submitPresentationJob(ctx.request.body) }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.get('/api/hermes/presentations/:jobId', async ctx => {
  try {
    ctx.body = { job: await getPresentationJob(ctx.params.jobId) }
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.get('/api/hermes/presentations/:jobId/download', async ctx => {
  try {
    const media = await getPresentationMedia(ctx.params.jobId)
    const encoded = encodeURIComponent(media.fileName)
    ctx.type = media.mime
    ctx.length = media.size
    ctx.set('Content-Disposition', `attachment; filename="presentation${media.fileName.slice(media.fileName.lastIndexOf('.'))}"; filename*=UTF-8''${encoded}`)
    ctx.body = media.stream
  } catch (error) {
    handleError(ctx, error)
  }
})

presentationRoutes.get('/api/hermes/presentations/:jobId/preview', async ctx => {
  try {
    const media = await getPresentationMedia(ctx.params.jobId, true)
    ctx.type = media.mime
    ctx.length = media.size
    if (media.mime.startsWith('text/html')) {
      ctx.set('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'self'")
    }
    ctx.set('Content-Disposition', `inline; filename*=UTF-8''${encodeURIComponent(media.fileName)}`)
    ctx.body = media.stream
  } catch (error) {
    handleError(ctx, error)
  }
})
