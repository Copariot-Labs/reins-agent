import { describe, expect, it } from 'vitest'
import { normalizeOfficeCreateRequest } from '../../packages/server/src/services/reins/office'

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
})
