import { describe, expect, it } from 'vitest'
import {
  reinsChatLanguageInstructions,
  reinsReasoningProgressSummary,
} from '../../packages/server/src/services/reins/chat-language'

describe('Reins chat language policy', () => {
  it('keeps user-visible progress in Simplified Chinese without exposing private reasoning', () => {
    const instructions = reinsChatLanguageInstructions()

    expect(instructions).toContain('Simplified-Chinese-first')
    expect(instructions).toContain('streamed reasoning summaries')
    expect(instructions).toContain('Do not emit English reasoning or thinking text')
    expect(instructions).toContain('Never expose private chain-of-thought')
    expect(instructions).toContain('final responses in Simplified Chinese by default')
  })

  it('uses Chinese-only summaries for visible reasoning progress', () => {
    expect(reinsReasoningProgressSummary()).toBe('正在理解您的需求，并确定需要使用的 Reins 功能。')
    expect(reinsReasoningProgressSummary(true)).toBe('已完成所需操作，正在检查并整理结果。')
  })
})
