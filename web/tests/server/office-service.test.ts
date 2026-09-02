import { describe, expect, it } from 'vitest'
import {
  cancelOfficeOperation,
  friendlyOfficeOperationError,
  getOfficeOperation,
  normalizeOfficeCreateRequest,
  normalizeOfficeImportRequest,
  shouldAskForOfficeClarification,
  shouldRequestOfficeOperationClarification,
  startOfficeCreateOperation,
  startOfficeRevisionOperation,
} from '../../packages/server/src/services/reins/office'
import { officeCreationNeedsClarification } from '../../packages/server/src/services/reins/office-clarification'

describe('Reins Office service', () => {
  it('recognizes a detailed Chinese creation request without asking again', () => {
    expect(officeCreationNeedsClarification(
      '为阳光社区编写2026年第三季度工作计划，重点包括防汛和垃圾分类。',
    )).toBe(false)
    expect(officeCreationNeedsClarification('创建一个文档')).toBe(true)
  })

  it('defaults document generation to Chinese', () => {
    expect(normalizeOfficeCreateRequest({
      format: 'docx',
      prompt: '生成社区通知',
      skill_id: 'community-notice',
    }).language).toBe('zh')
  })

  it('preserves a validated fixed workflow id on create requests', () => {
    expect(normalizeOfficeCreateRequest({
      format: 'pptx',
      prompt: 'Create a quarterly community report',
      language: 'zh',
      skill_id: 'community-ppt-report',
      presentation: { slide_count: 10 },
    })).toEqual({
      format: 'pptx',
      prompt: 'Create a quarterly community report',
      language: 'zh',
      skill_id: 'community-ppt-report',
      presentation: {
        style: 'auto',
        slide_count: 10,
        audience: 'general',
        detail: 'balanced',
      },
    })
  })

  it('rejects oversized workflow identifiers', () => {
    expect(() => normalizeOfficeCreateRequest({
      format: 'docx',
      prompt: 'Create a notice',
      skill_id: 'x'.repeat(121),
    })).toThrow('Office skill cannot exceed 120 characters')
  })

  it('normalizes an Office import and enforces the selected section', () => {
    expect(normalizeOfficeImportRequest(
      'word',
      'C:\\Temp\\upload.docx',
      'C:\\fakepath\\阳光社区工作计划.docx',
    )).toEqual({
      format: 'docx',
      source_path: 'C:\\Temp\\upload.docx',
      file_name: '阳光社区工作计划.docx',
    })

    expect(() => normalizeOfficeImportRequest(
      'xlsx',
      'C:\\Temp\\upload.xlsx',
      '阳光社区工作计划.docx',
    )).toThrow('only accepts .xlsx files')
  })

  it('turns OfficeCLI validation failures into actionable bilingual errors', () => {
    const error = friendlyOfficeOperationError(
      new Error('OfficeCLI found 3 layout issues'),
      'create',
      'layout_check',
    )

    expect(error.code).toBe('officecli_failed')
    expect(error.title_zh).toBe('文件生成或验证失败')
    expect(error.suggestion_zh).toContain('减少单页文字')
    expect(error.retryable).toBe(true)
  })

  it('explains repeated revision compatibility failures without blaming content length', () => {
    const error = friendlyOfficeOperationError(
      new Error('OfficeCliCommandError: unsupported paragraph property'),
      'revise',
      'officecli_apply',
    )

    expect(error.code).toBe('officecli_failed')
    expect(error.title_zh).toBe('文件修改未完成')
    expect(error.message_zh).toContain('原文件已完整保留')
    expect(error.suggestion_zh).toContain('重试相同要求')
    expect(error.suggestion_zh).not.toContain('减少单页文字')
  })

  it('explains that the original file is preserved after revision timeouts', () => {
    const error = friendlyOfficeOperationError(
      Object.assign(new Error('Office worker timed out'), { code: 'worker_timeout' }),
      'revise',
    )

    expect(error.code).toBe('timeout')
    expect(error.suggestion_zh).toContain('原文件不会因超时而丢失')
  })

  it('recognizes Python timeout types and hides nested command prompts', () => {
    const secretPrompt = '生成阳光社区工作计划并包含内部敏感内容'
    const error = friendlyOfficeOperationError(
      Object.assign(
        new Error(`TimeoutExpired: Command ['python', '-m', 'reins.main', '-z', '${secretPrompt}']`),
        { code: 'worker_error', workerErrorType: 'OfficeContentTimeoutError' },
      ),
      'create',
      'content_generation',
    )

    expect(error.code).toBe('timeout')
    expect(error.technical_detail).toBe('Reins content planning timed out before returning a result.')
    expect(error.technical_detail).not.toContain(secretPrompt)
    expect(error.suggestion_zh).toContain('无需重复补充相同内容')
  })

  it('explains how to release a Windows Office file lock', () => {
    const error = friendlyOfficeOperationError(
      new Error('[WinError 32] 另一个程序正在使用此文件，进程无法访问'),
      'revise',
      'file_ready',
    )

    expect(error.code).toBe('file_in_use')
    expect(error.message_zh).toContain('原文件已保留')
    expect(error.suggestion_zh).toContain('文件资源管理器预览窗格')
    expect(error.suggestion_en).toContain('File Explorer preview pane')
  })

  it('identifies a Windows OfficeCLI creation path handoff failure', () => {
    const error = friendlyOfficeOperationError(
      new Error("Error: Could not find file 'C:\\Users\\ss\\Documents\\Reins Workspace\\Word\\玫瑰湾社区工作计划.docx'."),
      'create',
      'officecli_prepare',
    )

    expect(error.code).toBe('workspace_path_failed')
    expect(error.title_zh).toContain('Windows 文件路径')
    expect(error.suggestion_zh).toContain('临时路径')
  })

  it('asks for clarification only for usable planning failures', () => {
    const invalidStructure = friendlyOfficeOperationError(
      new Error('Reins did not return a valid structured Word revision'),
      'revise',
      'revision_planning',
    )
    const unavailableModel = friendlyOfficeOperationError(
      new Error('Model provider connection unavailable'),
      'revise',
      'revision_planning',
    )

    expect(shouldAskForOfficeClarification(invalidStructure)).toBe(true)
    expect(shouldAskForOfficeClarification(unavailableModel)).toBe(false)
  })

  it('never replaces a selected fixed skill failure with a generic details question', () => {
    const invalidStructure = friendlyOfficeOperationError(
      new Error('Reins did not return a JSON object.'),
      'create',
      'content_generation',
    )

    expect(shouldRequestOfficeOperationClarification(
      invalidStructure,
      'create',
      '创建一个文档',
      'community-work-plan',
    )).toBe(false)
    expect(shouldRequestOfficeOperationClarification(
      invalidStructure,
      'create',
      '创建一个文档',
    )).toBe(true)
  })

  it('does not disguise Windows runtime failures as clarification questions', () => {
    const runtimeFailure = friendlyOfficeOperationError(
      new Error('spawn reins ENOENT'),
      'create',
      'content_generation',
    )
    const invalidHandle = friendlyOfficeOperationError(
      new Error('OSError: [WinError 6] The handle is invalid'),
      'create',
      'content_generation',
    )

    expect(runtimeFailure.code).toBe('runtime_unavailable')
    expect(runtimeFailure.title_zh).toBe('Office 服务暂时不可用')
    expect(shouldAskForOfficeClarification(runtimeFailure)).toBe(false)
    expect(invalidHandle.code).toBe('runtime_unavailable')
    expect(shouldAskForOfficeClarification(invalidHandle)).toBe(false)
  })

  it('directs missing model configuration to settings instead of asking for document details', () => {
    const missingModel = friendlyOfficeOperationError(
      new Error('No LLM provider configured. Run `reins model` to configure one.'),
      'create',
      'content_generation',
    )

    expect(missingModel.code).toBe('model_unavailable')
    expect(missingModel.suggestion_zh).toContain('模型设置')
    expect(shouldAskForOfficeClarification(missingModel)).toBe(false)
  })

  it('pauses vague Office page revisions for user input before starting a worker', () => {
    const started = startOfficeRevisionOperation('office-document-1', {
      instruction: '修改这个文件',
    })

    expect(started.status).toBe('needs_input')
    expect(started.error).toBeUndefined()
    expect(started.clarification).toEqual(expect.objectContaining({
      title_zh: '请补充具体修改要求',
      message_zh: expect.stringContaining('当前文件会保持不变'),
      example_zh: expect.stringContaining('第二部分'),
    }))
    expect(started.events.at(-1)).toEqual(expect.objectContaining({
      stage: 'needs_input',
      message_zh: '请补充具体修改要求',
    }))
    expect(getOfficeOperation(started.id)).toEqual(started)
  })

  it('cancels a queued Office page operation before its worker starts', async () => {
    const started = startOfficeCreateOperation(normalizeOfficeCreateRequest({
      format: 'xlsx',
      prompt: '创建社区筛选工作簿',
      skill_id: 'community-excel-filter',
    }))

    const cancelled = cancelOfficeOperation(started.id)
    expect(cancelled.status).toBe('cancelled')
    expect(cancelled.events.at(-1)).toEqual(expect.objectContaining({
      stage: 'cancelled',
      message_zh: expect.stringContaining('用户取消'),
    }))
    await Promise.resolve()
  })
})
