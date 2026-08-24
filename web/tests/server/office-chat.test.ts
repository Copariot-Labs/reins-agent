import { beforeEach, describe, expect, it, vi } from 'vitest'

const createOfficeDocumentMock = vi.fn()
const reviseOfficeDocumentMock = vi.fn()

vi.mock('../../packages/server/src/services/reins/office', () => ({
  createOfficeDocument: createOfficeDocumentMock,
  reviseOfficeDocument: reviseOfficeDocumentMock,
}))

const existingDocument = {
  id: 'deck-1',
  title: 'Launch Plan',
  kind: 'pptx' as const,
  path: '/office/launch-plan.pptx',
  file_name: 'launch-plan.pptx',
  mime_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  created_at: '2026-08-24T08:00:00Z',
  updated_at: '2026-08-24T08:00:00Z',
  revision_count: 0,
  prompt: 'create a launch plan',
  generator: 'reins',
  command_count: 20,
  metadata: {},
}

function officeToolMessage(document = existingDocument, toolName = 'reins_office_create') {
  return {
    role: 'tool',
    tool_name: toolName,
    content: JSON.stringify({ ok: true, office_document: document }),
  }
}

describe('Reins Office chat routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses the selected composer tool as the exact Office format', async () => {
    createOfficeDocumentMock.mockResolvedValue({ id: 'sheet-1', kind: 'xlsx' })
    const { createOfficeChatDocument } = await import('../../packages/server/src/services/reins/office-chat')

    const result = await createOfficeChatDocument('prepare next month expenses', 'spreadsheet')

    expect(createOfficeDocumentMock).toHaveBeenCalledWith({
      format: 'xlsx',
      prompt: 'prepare next month expenses',
      language: 'en',
    })
    expect(result.document).toEqual({ id: 'sheet-1', kind: 'xlsx' })
  })

  it('auto-detects Office requests without routing ordinary chat', async () => {
    const { inferOfficeChatFormat, mayNeedOfficeChat } = await import('../../packages/server/src/services/reins/office-chat')

    expect(mayNeedOfficeChat('create a sales presentation')).toBe(true)
    expect(inferOfficeChatFormat('create a sales presentation')).toBe('pptx')
    expect(mayNeedOfficeChat('what is a sales presentation?')).toBe(false)
    expect(mayNeedOfficeChat('hello, help me think')).toBe(false)
  })

  it('recognizes Chinese Office creation requests', async () => {
    const { inferOfficeChatFormat, mayNeedOfficeChat } = await import('../../packages/server/src/services/reins/office-chat')

    expect(mayNeedOfficeChat('帮我制作一个下周工作计划表格')).toBe(true)
    expect(inferOfficeChatFormat('帮我制作一个下周工作计划表格')).toBe('xlsx')
  })

  it('routes a follow-up revision to the same persisted Office document', async () => {
    const updatedDocument = {
      ...existingDocument,
      updated_at: '2026-08-24T08:05:00Z',
      revision_count: 1,
    }
    reviseOfficeDocumentMock.mockResolvedValue(updatedDocument)
    const {
      resolveOfficeChatRequest,
      runOfficeChatRequest,
    } = await import('../../packages/server/src/services/reins/office-chat')

    const request = resolveOfficeChatRequest(
      'modify the color. also write in more details',
      undefined,
      [officeToolMessage()],
    )

    expect(request).toEqual({ operation: 'revise', document: existingDocument })
    const result = await runOfficeChatRequest('modify the color. also write in more details', request!)
    expect(reviseOfficeDocumentMock).toHaveBeenCalledWith('deck-1', {
      instruction: 'modify the color. also write in more details',
    })
    expect(createOfficeDocumentMock).not.toHaveBeenCalled()
    expect(result.operation).toBe('revise')
    expect(result.document?.id).toBe('deck-1')
    expect(result.document?.path).toBe('/office/launch-plan.pptx')
    expect(result.document?.revision_count).toBe(1)
  })

  it('recovers the latest revised document from persisted chat history', async () => {
    const revisedDocument = {
      ...existingDocument,
      updated_at: '2026-08-24T08:10:00Z',
      revision_count: 2,
    }
    const { latestOfficeChatDocument } = await import('../../packages/server/src/services/reins/office-chat')

    expect(latestOfficeChatDocument([
      officeToolMessage(existingDocument, 'create_office_document'),
      officeToolMessage(revisedDocument, 'reins_office_revise'),
    ])).toEqual(revisedDocument)
  })

  it('creates a separate file only when the user explicitly asks for one', async () => {
    const { resolveOfficeChatRequest } = await import('../../packages/server/src/services/reins/office-chat')

    const request = resolveOfficeChatRequest(
      'create another presentation for the engineering team',
      'slides',
      [officeToolMessage()],
    )

    expect(request).toEqual({ operation: 'create', format: 'pptx' })
  })

  it('recognizes a natural formatting follow-up without reselecting the Office tool', async () => {
    const { resolveOfficeChatRequest } = await import('../../packages/server/src/services/reins/office-chat')

    const request = resolveOfficeChatRequest(
      'make the title bolder and use a more modern color palette',
      undefined,
      [officeToolMessage()],
    )

    expect(request).toEqual({ operation: 'revise', document: existingDocument })
  })
})
