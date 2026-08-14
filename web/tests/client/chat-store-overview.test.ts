// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  fetchSessions: vi.fn(),
  resumeSession: vi.fn(),
}))

vi.mock('@/api/hermes/chat', () => ({
  startRunViaSocket: vi.fn(),
  resumeSession: mocks.resumeSession,
  registerSessionHandlers: vi.fn(),
  unregisterSessionHandlers: vi.fn(),
  getChatRunSocket: vi.fn(() => ({ emit: vi.fn() })),
  respondToolApproval: vi.fn(),
  respondClarify: vi.fn(),
  onPeerUserMessage: vi.fn(() => vi.fn()),
  onSessionCommand: vi.fn(() => vi.fn()),
}))

vi.mock('@/api/client', () => ({
  getActiveProfileName: () => 'default',
}))

vi.mock('@/api/hermes/sessions', () => ({
  deleteSession: vi.fn(),
  fetchSessionMessagesPage: vi.fn(),
  fetchSessions: mocks.fetchSessions,
  setSessionModel: vi.fn(),
}))

vi.mock('@/api/hermes/download', () => ({
  getDownloadUrl: (_path: string, name: string) => `/download/${name}`,
}))

vi.mock('@/utils/completion-sound', () => ({
  primeCompletionSound: vi.fn(),
  playCompletionSound: vi.fn(),
}))

import { useChatStore } from '@/stores/hermes/chat'

const summaries = [
  {
    id: 'latest-task',
    profile: 'default',
    title: 'Latest task',
    source: 'cli',
    started_at: 10,
    last_active: 20,
    ended_at: null,
    message_count: 2,
    input_tokens: 0,
    output_tokens: 0,
  },
]

describe('chat task overview loading', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
    setActivePinia(createPinia())
    mocks.fetchSessions.mockResolvedValue(summaries)
    mocks.resumeSession.mockImplementation((sessionId: string, onResumed: (data: any) => void) => {
      onResumed({ session_id: sessionId, messages: [], events: [], isWorking: false })
    })
  })

  it('loads task summaries without automatically opening the latest task', async () => {
    const store = useChatStore()

    await store.loadSessions()

    expect(store.sessions.map(session => session.id)).toEqual(['latest-task'])
    expect(store.activeSessionId).toBeNull()
    expect(store.activeSession).toBeNull()
    expect(mocks.resumeSession).not.toHaveBeenCalled()
  })

  it('still opens a task when its route supplies the session id', async () => {
    const store = useChatStore()

    await store.loadSessions(null, 'latest-task')

    expect(store.activeSessionId).toBe('latest-task')
    expect(store.activeSession?.id).toBe('latest-task')
    expect(mocks.resumeSession).toHaveBeenCalledWith(
      'latest-task',
      expect.any(Function),
      'default',
    )
  })
})
