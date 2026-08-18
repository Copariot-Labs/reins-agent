import { describe, expect, it } from 'vitest'

import { getSystemPrompt } from '../../packages/server/src/lib/llm-prompt'

describe('Reins system prompt branding', () => {
  it('makes Reins the only user-facing assistant identity', () => {
    const prompt = getSystemPrompt('Keep this custom instruction.')

    expect(prompt).toContain('You are Reins Agent')
    expect(prompt).toContain('Keep this custom instruction.')
    expect(prompt).not.toContain('Hermes Agent')
    expect(prompt).not.toContain('Nous Research')
    expect(prompt.indexOf('Keep this custom instruction.')).toBeLessThan(prompt.indexOf('You are Reins Agent'))
  })
})
