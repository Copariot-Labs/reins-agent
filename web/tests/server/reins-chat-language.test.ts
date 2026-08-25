import { describe, expect, it } from 'vitest'
import { reinsChatLanguageInstructions } from '../../packages/server/src/services/reins/chat-language'

describe('Reins chat language policy', () => {
  it('keeps user-visible progress in Simplified Chinese without exposing private reasoning', () => {
    const instructions = reinsChatLanguageInstructions()

    expect(instructions).toContain('Simplified-Chinese-first')
    expect(instructions).toContain('streamed reasoning summaries')
    expect(instructions).toContain('Do not emit English reasoning or thinking text')
    expect(instructions).toContain('Never expose private chain-of-thought')
    expect(instructions).toContain('final responses in Simplified Chinese by default')
  })
})
