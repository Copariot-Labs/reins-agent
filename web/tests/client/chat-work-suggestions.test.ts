import { describe, expect, it } from 'vitest'
import {
  getWorkSuggestions,
  getOfficeFormatOptions,
  getWorkToolOptions,
  shouldShowNewChatSuggestions,
} from '@/components/hermes/chat/work-suggestions'

describe('chat work suggestions', () => {
  it('groups all Office formats under the document category', () => {
    expect(getWorkToolOptions(false).map(option => option.id)).toEqual([
      'document',
      'research',
      'browser',
    ])
    expect(getOfficeFormatOptions(false).map(option => option.id)).toEqual([
      'document',
      'spreadsheet',
      'slides',
    ])
  })

  it('offers Reins-specific document prompts that route through Office creation', () => {
    const suggestions = getWorkSuggestions('document', false)

    expect(suggestions.map(suggestion => suggestion.label)).toContain('Reins Agent Report')
    expect(suggestions.map(suggestion => suggestion.label)).toContain('Monitoring Incident Report')
    expect(suggestions.every(suggestion => suggestion.prompt.toLowerCase().includes('document'))).toBe(true)
  })

  it('shows suggestions in a new client-created chat', () => {
    expect(shouldShowNewChatSuggestions({
      hasSession: true,
      title: '',
      visibleMessageCount: 0,
      isLoadingMessages: true,
    })).toBe(true)
  })

  it('hides suggestions as soon as the chat contains a visible message', () => {
    expect(shouldShowNewChatSuggestions({
      hasSession: true,
      title: '',
      visibleMessageCount: 1,
      isLoadingMessages: false,
    })).toBe(false)
  })

  it('hides suggestions for existing chats before their messages finish loading', () => {
    expect(shouldShowNewChatSuggestions({
      hasSession: true,
      title: 'Weekly operations report',
      messageCount: 5,
      visibleMessageCount: 0,
      isLoadingMessages: true,
    })).toBe(false)

    expect(shouldShowNewChatSuggestions({
      hasSession: true,
      title: 'Weekly operations report',
      visibleMessageCount: 0,
      isLoadingMessages: true,
    })).toBe(false)
  })

  it('shows suggestions for an empty titled chat after loading finishes', () => {
    expect(shouldShowNewChatSuggestions({
      hasSession: true,
      title: 'New Office task',
      visibleMessageCount: 0,
      isLoadingMessages: false,
    })).toBe(true)
  })
})
