import { describe, expect, it } from 'vitest'
import { visibleReinsReasoning } from '@/utils/reins-reasoning'

describe('visibleReinsReasoning', () => {
  it('preserves Chinese reasoning summaries', () => {
    expect(visibleReinsReasoning('正在查询最近的工单。')).toBe('正在查询最近的工单。')
  })

  it('replaces English-only reasoning before a tool call', () => {
    expect(visibleReinsReasoning('The user wants the latest five work orders.'))
      .toBe('正在理解您的需求，并确定需要使用的 Reins 功能。')
  })

  it('replaces English-only reasoning after response content arrives', () => {
    expect(visibleReinsReasoning('I got the data and will format it.', true))
      .toBe('已完成所需操作，正在检查并整理结果。')
  })
})
