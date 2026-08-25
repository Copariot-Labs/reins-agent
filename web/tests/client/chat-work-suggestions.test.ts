import { describe, expect, it } from 'vitest'
import {
  getWorkSuggestions,
  getOfficeFormatOptions,
  getWorkToolOptions,
  routedWorkTool,
  shouldShowNewChatSuggestions,
} from '@/components/hermes/chat/work-suggestions'

describe('chat work suggestions', () => {
  it('groups all Office formats under the document category', () => {
    expect(getWorkToolOptions(false).map(option => option.id)).toEqual([
      'document',
      'finance',
      'work-orders',
      'research',
      'browser',
    ])
    expect(getOfficeFormatOptions(false).map(option => option.id)).toEqual([
      'document',
      'spreadsheet',
      'slides',
    ])
  })

  it('offers Chinese Finance prompts that stay on the native chat route', () => {
    const suggestions = getWorkSuggestions('finance', true)

    expect(suggestions.map(suggestion => suggestion.label)).toEqual(expect.arrayContaining([
      '记录支出',
      '记录收入',
      '本月财务汇总',
      '导出财务 Excel',
    ]))
    expect(suggestions.every(suggestion => /财务|收入|支出/.test(suggestion.prompt))).toBe(true)
    expect(routedWorkTool('finance')).toBeUndefined()
  })

  it('offers Chinese Work Orders queries, export, and report examples', () => {
    const suggestions = getWorkSuggestions('work-orders', true)

    expect(suggestions.map(suggestion => suggestion.label)).toEqual(expect.arrayContaining([
      '本月工单汇总',
      '紧急待处理工单',
      '更新工单',
      '导出工单 Excel',
      '生成工单报告',
    ]))
    expect(suggestions.every(suggestion => suggestion.prompt.includes('工单'))).toBe(true)
    expect(routedWorkTool('work-orders')).toBeUndefined()
    expect(routedWorkTool('document')).toBe('document')
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
