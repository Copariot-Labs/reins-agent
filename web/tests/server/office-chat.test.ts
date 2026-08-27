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

    const result = await createOfficeChatDocument(
      'prepare next month expenses',
      'spreadsheet',
      'community-excel-summary',
    )

    expect(createOfficeDocumentMock).toHaveBeenCalledWith({
      format: 'xlsx',
      prompt: 'prepare next month expenses',
      language: 'en',
      skill_id: 'community-excel-summary',
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

  it('routes natural Office creation wording directly to OfficeCLI', async () => {
    const { inferOfficeChatFormat, mayNeedOfficeChat } = await import('../../packages/server/src/services/reins/office-chat')

    expect(mayNeedOfficeChat('整理8月社区两委联席会议纪要，议题包括防汛值班和停车治理。')).toBe(true)
    expect(inferOfficeChatFormat('整理8月社区两委联席会议纪要')).toBe('docx')
    expect(mayNeedOfficeChat('帮我出一份社区防汛工作简报')).toBe(true)
    expect(inferOfficeChatFormat('帮我出一份社区防汛工作简报')).toBe('docx')
    expect(mayNeedOfficeChat('Put together a Word briefing for the quarterly review')).toBe(true)
    expect(inferOfficeChatFormat('Put together a Word briefing for the quarterly review')).toBe('docx')
    expect(mayNeedOfficeChat('Convert this quarterly summary into a Word document')).toBe(true)
    expect(mayNeedOfficeChat('I need a Word version of the quarterly work plan')).toBe(true)
    expect(mayNeedOfficeChat('给我弄个Word版季度工作方案')).toBe(true)
    expect(mayNeedOfficeChat('将这份内容导出为PPT')).toBe(true)
    expect(mayNeedOfficeChat('把这些想法整理一下')).toBe(false)
    expect(mayNeedOfficeChat('what is a Word document?')).toBe(false)
    expect(mayNeedOfficeChat('如何制作一个PPT？')).toBe(false)
  })

  it('forbids the general agent from building Office files another way', async () => {
    const { reinsOfficeAgentInstructions } = await import('../../packages/server/src/services/reins/office-chat')

    const instructions = reinsOfficeAgentInstructions()
    expect(instructions).toContain('bundled OfficeCLI are the only allowed path')
    expect(instructions).toContain('Never use terminal commands')
    expect(instructions).toContain('package installation')
    expect(instructions).toContain('ask only whether the user wants Word, Excel, or PPT')
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

  it('routes document translation follow-ups through the same Office document', async () => {
    const { resolveOfficeChatRequest } = await import('../../packages/server/src/services/reins/office-chat')

    expect(resolveOfficeChatRequest(
      'translate this into chinese. i need chinse version',
      undefined,
      [officeToolMessage()],
    )).toEqual({ operation: 'revise', document: existingDocument })
    expect(resolveOfficeChatRequest(
      '把这个文档翻译成中文版本',
      undefined,
      [officeToolMessage()],
    )).toEqual({ operation: 'revise', document: existingDocument })
  })

  it('lets Reins semantically route uncommon Office follow-ups', async () => {
    const { resolveOfficeChatRequestWithBrain } = await import('../../packages/server/src/services/reins/office-chat')
    const classifier = vi.fn().mockResolvedValue({
      intent: 'revise',
      confidence: 0.88,
    })

    const request = await resolveOfficeChatRequestWithBrain(
      'give the previous file a fresher voice',
      undefined,
      [officeToolMessage()],
      classifier,
    )

    expect(classifier).toHaveBeenCalledWith('give the previous file a fresher voice', existingDocument)
    expect(request).toEqual({ operation: 'revise', document: existingDocument })
  })

  it('keeps ordinary conversation out of Office when Reins selects chat', async () => {
    const { resolveOfficeChatRequestWithBrain } = await import('../../packages/server/src/services/reins/office-chat')

    const request = await resolveOfficeChatRequestWithBrain(
      'what should I work on next?',
      undefined,
      [officeToolMessage()],
      vi.fn().mockResolvedValue({ intent: 'chat', confidence: 0.94 }),
    )

    expect(request).toBeNull()
  })

  it('recovers a workspace document by its path when chat history has no Office tool', async () => {
    const workspaceDocument = {
      ...existingDocument,
      id: 'workspace-doc-1',
      title: '社区防汛方案',
      path: '/Users/mei/Documents/Reins Workspace/Word/社区防汛方案.docx',
      file_name: '社区防汛方案.docx',
    }
    const { resolveIndexedOfficeRevisionDocument } = await import('../../packages/server/src/services/reins/office-chat')

    expect(resolveIndexedOfficeRevisionDocument(
      '请修改这个文件的标题颜色：[Attached file: 社区防汛方案.docx; local path: /Users/mei/Documents/Reins Workspace/Word/社区防汛方案.docx]',
      [existingDocument, workspaceDocument],
    )).toEqual(workspaceDocument)
  })

  it('uses the latest indexed document for a generic Office revision follow-up', async () => {
    const latestDocument = {
      ...existingDocument,
      id: 'latest-doc',
      path: '/Users/mei/Documents/Reins Workspace/PowerPoint/latest.pptx',
      file_name: 'latest.pptx',
      updated_at: '2026-08-25T08:00:00Z',
    }
    const { resolveIndexedOfficeRevisionDocument } = await import('../../packages/server/src/services/reins/office-chat')

    expect(resolveIndexedOfficeRevisionDocument(
      'modify the design and use a warmer color palette',
      [existingDocument, latestDocument],
      'slides',
    )).toEqual(latestDocument)
  })

  it('does not revise a different document when an explicit filename is unmatched', async () => {
    const { resolveIndexedOfficeRevisionDocument } = await import('../../packages/server/src/services/reins/office-chat')

    expect(resolveIndexedOfficeRevisionDocument(
      'modify missing-report.docx and add more details',
      [existingDocument],
    )).toBeNull()
  })

  it('asks a focused Chinese clarification question without exposing an error', async () => {
    const { officeClarificationPrompt } = await import('../../packages/server/src/services/reins/office-chat')

    const prompt = officeClarificationPrompt(
      { operation: 'revise', document: existingDocument },
      '修改这个文档',
    )

    expect(prompt).toContain('要修改哪个部分')
    expect(prompt).toContain('哪些内容必须保持不变')
    expect(prompt).not.toContain('失败')
    expect(prompt).not.toContain('OfficeCLI')
  })

  it('continues the pending Office revision when the user supplies clarification', async () => {
    const clarificationToolMessage = {
      role: 'tool',
      tool_name: 'reins_office_revise',
      content: JSON.stringify({
        ok: false,
        needs_clarification: true,
        office_document: existingDocument,
      }),
    }
    const { resolveOfficeChatRequest } = await import('../../packages/server/src/services/reins/office-chat')

    expect(resolveOfficeChatRequest(
      '标题和第二部分，标题改成红色，其他内容保持不变',
      undefined,
      [clarificationToolMessage],
    )).toEqual({ operation: 'revise', document: existingDocument })
    expect(resolveOfficeChatRequest(
      '取消',
      undefined,
      [clarificationToolMessage],
    )).toBeNull()
  })

  it('continues a pending Office creation with the original fixed skill', async () => {
    createOfficeDocumentMock.mockResolvedValue({ id: 'minutes-1', kind: 'docx' })
    const clarificationToolMessage = {
      role: 'tool',
      tool_name: 'reins_office_create',
      content: JSON.stringify({
        ok: false,
        needs_clarification: true,
        pending_create: {
          format: 'docx',
          prompt: '整理8月社区两委联席会议纪要，议题包括防汛值班和停车治理。',
          skill_id: 'community-meeting-minutes',
        },
      }),
    }
    const {
      resolveOfficeChatRequest,
      runOfficeChatRequest,
    } = await import('../../packages/server/src/services/reins/office-chat')

    const request = resolveOfficeChatRequest(
      '用于正式归档，缺少的会议基本信息请标注待补充。',
      undefined,
      [clarificationToolMessage],
    )

    expect(request).toEqual({
      operation: 'create',
      format: 'docx',
      original_prompt: '整理8月社区两委联席会议纪要，议题包括防汛值班和停车治理。',
      skill_id: 'community-meeting-minutes',
    })

    await runOfficeChatRequest(
      '用于正式归档，缺少的会议基本信息请标注待补充。',
      request!,
    )

    expect(createOfficeDocumentMock).toHaveBeenCalledWith(expect.objectContaining({
      format: 'docx',
      skill_id: 'community-meeting-minutes',
      language: 'zh',
      prompt: expect.stringContaining('用户补充信息'),
    }))
    expect(createOfficeDocumentMock.mock.calls[0][0].prompt).toContain('防汛值班和停车治理')
    expect(createOfficeDocumentMock.mock.calls[0][0].prompt).toContain('用于正式归档')
  })

  it('detects vague revision commands before starting the Office worker', async () => {
    const { officeRevisionNeedsClarification } = await import('../../packages/server/src/services/reins/office-chat')

    expect(officeRevisionNeedsClarification('修改这个文件')).toBe(true)
    expect(officeRevisionNeedsClarification('Please improve this document')).toBe(true)
    expect(officeRevisionNeedsClarification('把标题改成红色，第二部分增加两个案例')).toBe(false)
  })
})
