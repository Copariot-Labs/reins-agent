import { describe, expect, it } from 'vitest'
import {
  cancelOfficeOperation,
  friendlyOfficeOperationError,
  normalizeOfficeCreateRequest,
  startOfficeCreateOperation,
} from '../../packages/server/src/services/reins/office'

describe('Reins Office service', () => {
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

  it('explains that the original file is preserved after revision timeouts', () => {
    const error = friendlyOfficeOperationError(
      Object.assign(new Error('Office worker timed out'), { code: 'worker_timeout' }),
      'revise',
    )

    expect(error.code).toBe('timeout')
    expect(error.suggestion_zh).toContain('原文件不会因超时而丢失')
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
