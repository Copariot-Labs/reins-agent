import { beforeEach, describe, expect, it, vi } from 'vitest'

const createOfficeDocumentMock = vi.fn()

vi.mock('../../packages/server/src/services/reins/office', () => ({
  createOfficeDocument: createOfficeDocumentMock,
}))

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
})
