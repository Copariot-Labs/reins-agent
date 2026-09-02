import Router from '@koa/router'
import { mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  cancelOfficeOperation,
  createOfficeDocument,
  getOfficeOperation,
  getOfficePreviewPath,
  getOfficeStatus,
  importOfficeDocument,
  listOfficeDocuments,
  listOfficeSkills,
  normalizeOfficeCreateRequest,
  normalizeOfficeRevisionRequest,
  reviseOfficeDocument,
  startOfficeCreateOperation,
  startOfficeRevisionOperation,
} from '../../services/reins/office'

export const officeRoutes = new Router()

const MAX_OFFICE_IMPORT_SIZE = 50 * 1024 * 1024

function multipartBoundary(contentType: string): Buffer | null {
  const match = contentType.match(/boundary=(?:"([^"]+)"|([^;]+))/i)
  const value = (match?.[1] || match?.[2] || '').trim()
  return value ? Buffer.from(`--${value}`) : null
}

function splitMultipart(raw: Buffer, boundary: Buffer): Buffer[] {
  const parts: Buffer[] = []
  let start = 0
  while (true) {
    const index = raw.indexOf(boundary, start)
    if (index === -1) break
    if (start > 0) parts.push(raw.subarray(start + 2, index))
    start = index + boundary.length
  }
  return parts
}

function multipartFile(raw: Buffer, boundary: Buffer): { name: string, data: Buffer } | null {
  for (const part of splitMultipart(raw, boundary)) {
    const headerEnd = part.indexOf(Buffer.from('\r\n\r\n'))
    if (headerEnd === -1) continue
    const header = part.subarray(0, headerEnd).toString('utf8')
    const filenameStar = header.match(/filename\*=UTF-8''([^;\r\n]+)/i)
    const filenamePlain = header.match(/filename="([^"]+)"/i)
    let name = ''
    try {
      name = filenameStar
        ? decodeURIComponent(filenameStar[1])
        : String(filenamePlain?.[1] || '')
    } catch {
      name = ''
    }
    if (!name) continue
    return {
      name,
      data: part.subarray(headerEnd + 4, part.length - 2),
    }
  }
  return null
}

function handleError(ctx: any, err: any) {
  const code = String(err?.code || 'internal_error')
  const statusByCode: Record<string, number> = {
    invalid_request: 400,
    file_too_large: 413,
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

officeRoutes.get('/api/reins/office/skills', async ctx => {
  try {
    ctx.body = { skills: await listOfficeSkills(ctx.query.format) }
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

officeRoutes.post('/api/reins/office/operations', async ctx => {
  try {
    const input = normalizeOfficeCreateRequest(ctx.request.body)
    ctx.status = 202
    ctx.body = { operation: startOfficeCreateOperation(input) }
  } catch (err) {
    handleError(ctx, err)
  }
})

officeRoutes.get('/api/reins/office/operations/:id', ctx => {
  try {
    ctx.body = { operation: getOfficeOperation(ctx.params.id) }
  } catch (err) {
    handleError(ctx, err)
  }
})

officeRoutes.post('/api/reins/office/operations/:id/cancel', ctx => {
  try {
    ctx.body = { operation: cancelOfficeOperation(ctx.params.id) }
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

officeRoutes.post('/api/reins/office/import', async ctx => {
  let temporaryDirectory = ''
  try {
    const contentType = ctx.get('content-type') || ''
    if (!contentType.toLowerCase().startsWith('multipart/form-data')) {
      throw Object.assign(new Error('Expected multipart/form-data.'), { code: 'invalid_request' })
    }
    const boundary = multipartBoundary(contentType)
    if (!boundary) {
      throw Object.assign(new Error('The Office upload boundary is missing.'), { code: 'invalid_request' })
    }

    const chunks: Buffer[] = []
    let totalSize = 0
    for await (const chunk of ctx.req) {
      totalSize += chunk.length
      if (totalSize > MAX_OFFICE_IMPORT_SIZE + 1024 * 1024) {
        throw Object.assign(new Error('Office files cannot exceed 50 MB.'), { code: 'file_too_large' })
      }
      chunks.push(chunk)
    }
    const upload = multipartFile(Buffer.concat(chunks), boundary)
    if (!upload || !upload.data.length) {
      throw Object.assign(new Error('Select an Office file to import.'), { code: 'invalid_request' })
    }
    if (upload.data.length > MAX_OFFICE_IMPORT_SIZE) {
      throw Object.assign(new Error('Office files cannot exceed 50 MB.'), { code: 'file_too_large' })
    }

    const format = String(ctx.query.format || '').trim().toLowerCase()
    const safeSuffix = ['docx', 'xlsx', 'pptx'].includes(format) ? format : 'office'
    temporaryDirectory = await mkdtemp(join(tmpdir(), 'reins-office-import-'))
    const temporaryPath = join(temporaryDirectory, `upload.${safeSuffix}`)
    await writeFile(temporaryPath, upload.data, { flag: 'wx' })
    const document = await importOfficeDocument(format, temporaryPath, upload.name)
    ctx.status = 201
    ctx.body = { document }
  } catch (err) {
    handleError(ctx, err)
  } finally {
    if (temporaryDirectory) {
      await rm(temporaryDirectory, { recursive: true, force: true }).catch(() => undefined)
    }
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

officeRoutes.post('/api/reins/office/documents/:id/revision-operations', async ctx => {
  try {
    const input = normalizeOfficeRevisionRequest(ctx.request.body)
    ctx.status = 202
    ctx.body = { operation: startOfficeRevisionOperation(ctx.params.id, input) }
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
