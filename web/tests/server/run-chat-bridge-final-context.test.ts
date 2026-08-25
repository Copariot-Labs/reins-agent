import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSystemPromptMock = vi.fn()
const getSessionMock = vi.fn()
const createSessionMock = vi.fn()
const addMessageMock = vi.fn()
const updateSessionMock = vi.fn()
const updateSessionStatsMock = vi.fn()
const getLatestToolMessageMock = vi.fn()
const updateUsageMock = vi.fn()
const buildCompressedHistoryMock = vi.fn()
const buildDbHistoryMock = vi.fn()
const buildSnapshotAwareHistoryMock = vi.fn(async (_sessionId: string, _profile: string, history: any[]) => history)
const pushStateMock = vi.fn()
const replaceStateMock = vi.fn()
const forceCompressBridgeHistoryMock = vi.fn()
const calcAndUpdateUsageMock = vi.fn()
const estimateUsageTokensFromMessagesMock = vi.fn()
const updateContextTokenUsageMock = vi.fn((sid: string, state: any, emit: any, contextTokens: number, usage?: { inputTokens: number; outputTokens: number }) => {
  state.contextTokens = contextTokens
  emit('usage.updated', {
    event: 'usage.updated',
    session_id: sid,
    inputTokens: usage?.inputTokens ?? state.inputTokens ?? 0,
    outputTokens: usage?.outputTokens ?? state.outputTokens ?? 0,
    contextTokens,
  })
  return contextTokens
})
const getCachedBridgeContextOverheadMock = vi.fn(() => undefined)
const contextTokensWithCachedOverheadMock = vi.fn((_state: any, messageTokens: number) => messageTokens)
const updateMessageContextTokenUsageMock = vi.fn((sid: string, state: any, emit: any, messageTokens: number, usage?: { inputTokens: number; outputTokens: number }) => updateContextTokenUsageMock(sid, state, emit, messageTokens, usage))
const flushBridgePendingToDbMock = vi.fn()
const ensureOpenBridgeAssistantMessageMock = vi.fn()
const syncBridgeReasoningToMessageMock = vi.fn()
const recordBridgeToolStartedMock = vi.fn()
const recordBridgeToolCompletedMock = vi.fn()
const resolveBridgeRunModelConfigMock = vi.fn()
const resolveOfficeChatRequestMock = vi.fn()
const resolveIndexedOfficeRevisionDocumentMock = vi.fn()
const officeClarificationPromptMock = vi.fn()
const officeRevisionNeedsClarificationMock = vi.fn()
const runOfficeChatRequestMock = vi.fn()
const hasOfficeRevisionIntentMock = vi.fn()
const listOfficeDocumentsMock = vi.fn()
const friendlyOfficeOperationErrorMock = vi.fn()
const shouldAskForOfficeClarificationMock = vi.fn()
const prepareBrowserForRunMock = vi.fn()

vi.mock('../../packages/server/src/lib/llm-prompt', () => ({
  getSystemPrompt: getSystemPromptMock,
}))

vi.mock('../../packages/server/src/db/hermes/session-store', () => ({
  getSession: getSessionMock,
  createSession: createSessionMock,
  addMessage: addMessageMock,
  updateSession: updateSessionMock,
  updateSessionStats: updateSessionStatsMock,
  getLatestToolMessage: getLatestToolMessageMock,
}))

vi.mock('../../packages/server/src/db/hermes/usage-store', () => ({
  updateUsage: updateUsageMock,
}))

vi.mock('../../packages/server/src/services/logger', () => ({
  logger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
  bridgeLogger: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}))

vi.mock('../../packages/server/src/services/hermes/run-chat/compression', () => ({
  buildCompressedHistory: buildCompressedHistoryMock,
  buildDbHistory: buildDbHistoryMock,
  buildSnapshotAwareHistory: buildSnapshotAwareHistoryMock,
  pushState: pushStateMock,
  replaceState: replaceStateMock,
  forceCompressBridgeHistory: forceCompressBridgeHistoryMock,
}))

vi.mock('../../packages/server/src/services/hermes/run-chat/usage', () => ({
  calcAndUpdateUsage: calcAndUpdateUsageMock,
  estimateUsageTokensFromMessages: estimateUsageTokensFromMessagesMock,
  getCachedBridgeContextOverhead: getCachedBridgeContextOverheadMock,
  contextTokensWithCachedOverhead: contextTokensWithCachedOverheadMock,
  updateContextTokenUsage: updateContextTokenUsageMock,
  updateMessageContextTokenUsage: updateMessageContextTokenUsageMock,
}))

vi.mock('../../packages/server/src/services/hermes/run-chat/bridge-message', () => ({
  flushBridgePendingToDb: flushBridgePendingToDbMock,
  ensureOpenBridgeAssistantMessage: ensureOpenBridgeAssistantMessageMock,
  syncBridgeReasoningToMessage: syncBridgeReasoningToMessageMock,
  recordBridgeToolStarted: recordBridgeToolStartedMock,
  recordBridgeToolCompleted: recordBridgeToolCompletedMock,
}))

vi.mock('../../packages/server/src/services/hermes/run-chat/model-config', () => ({
  resolveBridgeRunModelConfig: resolveBridgeRunModelConfigMock,
}))

vi.mock('../../packages/server/src/services/reins/office-chat', () => ({
  resolveOfficeChatRequest: resolveOfficeChatRequestMock,
  resolveIndexedOfficeRevisionDocument: resolveIndexedOfficeRevisionDocumentMock,
  officeClarificationPrompt: officeClarificationPromptMock,
  officeRevisionNeedsClarification: officeRevisionNeedsClarificationMock,
  runOfficeChatRequest: runOfficeChatRequestMock,
  hasOfficeRevisionIntent: hasOfficeRevisionIntentMock,
  OFFICE_CHAT_TOOL_NAMES: [
    'reins_office_create',
    'reins_office_revise',
    'create_office_document',
    'revise_office_document',
  ],
  REINS_OFFICE_CREATE_TOOL: 'reins_office_create',
  REINS_OFFICE_REVISE_TOOL: 'reins_office_revise',
}))

vi.mock('../../packages/server/src/services/reins/office', () => ({
  listOfficeDocuments: listOfficeDocumentsMock,
  friendlyOfficeOperationError: friendlyOfficeOperationErrorMock,
  shouldAskForOfficeClarification: shouldAskForOfficeClarificationMock,
}))

vi.mock('../../packages/server/src/services/hermes/browser-connection', () => ({
  prepareBrowserForRun: prepareBrowserForRunMock,
}))

function makeSocket() {
  return {
    connected: true,
    emit: vi.fn(),
    join: vi.fn(),
    to: vi.fn(() => ({ emit: vi.fn() })),
  } as any
}

function makeNamespace(emit: ReturnType<typeof vi.fn>) {
  const room = new Set(['socket-1'])
  return {
    adapter: { rooms: new Map([['session:session-1', room]]) },
    to: vi.fn(() => ({ emit })),
  } as any
}

function makeState() {
  return {
    messages: [],
    isWorking: false,
    events: [],
    queue: [],
  } as any
}

describe('bridge run final context usage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSystemPromptMock.mockReturnValue('system prompt')
    getSessionMock.mockReturnValue({ id: 'session-1', profile: 'default', model: '', provider: '' })
    resolveBridgeRunModelConfigMock.mockResolvedValue({ model: 'gpt-test', provider: 'openai' })
    resolveOfficeChatRequestMock.mockReturnValue(null)
    resolveIndexedOfficeRevisionDocumentMock.mockReturnValue(null)
    officeClarificationPromptMock.mockReturnValue('请告诉我要修改的部分、目标内容和需要保留的内容。')
    officeRevisionNeedsClarificationMock.mockReturnValue(false)
    runOfficeChatRequestMock.mockResolvedValue({ handled: false, message: '', exit_code: 0, document: null })
    hasOfficeRevisionIntentMock.mockReturnValue(false)
    listOfficeDocumentsMock.mockResolvedValue([])
    friendlyOfficeOperationErrorMock.mockReturnValue({
      code: 'worker_error',
      title_zh: 'Office 处理失败',
      title_en: 'Office processing failed',
      message_zh: 'Office 处理失败',
      message_en: 'Office processing failed',
      suggestion_zh: '请重试',
      suggestion_en: 'Try again',
      technical_detail: 'worker error',
    })
    shouldAskForOfficeClarificationMock.mockReturnValue(false)
    getLatestToolMessageMock.mockReturnValue(null)
    prepareBrowserForRunMock.mockResolvedValue(null)
    recordBridgeToolStartedMock.mockReturnValue({
      id: 'office-tool-1',
      name: 'reins_office_create',
      arguments: '{"prompt":"create a maintenance report document"}',
    })
    recordBridgeToolCompletedMock.mockReturnValue({
      id: 'office-tool-1',
      output: '{"ok":true}',
      duration: 0.2,
    })
    buildCompressedHistoryMock.mockResolvedValue([{ role: 'user', content: 'previous' }])
    buildDbHistoryMock.mockResolvedValue([
      { role: 'user', content: 'hello' },
      { role: 'assistant', content: 'done' },
    ])
    buildSnapshotAwareHistoryMock.mockImplementation(async (_sessionId: string, _profile: string, history: any[]) => history)
    calcAndUpdateUsageMock.mockResolvedValue({ inputTokens: 11, outputTokens: 7 })
    estimateUsageTokensFromMessagesMock.mockReturnValue({ inputTokens: 11, outputTokens: 7 })
    getCachedBridgeContextOverheadMock.mockImplementation((state: any) => {
      const fixed = state?.bridgeContext?.fixedContextTokens
      return typeof fixed === 'number' ? fixed : undefined
    })
    contextTokensWithCachedOverheadMock.mockImplementation((state: any, messageTokens: number) => {
      const fixed = state?.bridgeContext?.fixedContextTokens
      return typeof fixed === 'number' ? fixed + messageTokens : messageTokens
    })
    updateMessageContextTokenUsageMock.mockImplementation((sid: string, state: any, emit: any, messageTokens: number, usage?: { inputTokens: number; outputTokens: number }) => {
      const contextTokens = contextTokensWithCachedOverheadMock(state, messageTokens)
      return updateContextTokenUsageMock(sid, state, emit, contextTokens, usage)
    })
  })

  it('refreshes full context tokens when a bridge run completes', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 12345,
        fixed_context_tokens: 12327,
        message_count: 2,
        tool_count: 4,
        system_prompt_chars: 13,
      }),
      streamOutput: vi.fn(async function* () {
        yield { run_id: 'run-1', done: true, status: 'completed', output: 'done' }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: '记录一笔午餐支出30元', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(prepareBrowserForRunMock).toHaveBeenCalledWith('default', {
      browser: { mode: 'backend' },
      computer_use: { enabled: false },
    })
    expect(bridge.contextEstimate).toHaveBeenCalledWith(
      'session-1',
      [],
      expect.stringContaining('[Current Reins profile: default]'),
      'default',
      {
        model: 'gpt-test',
        provider: 'openai',
        capabilities: {
          browser: { mode: 'backend' },
          computer_use: { enabled: false },
        },
      },
    )
    expect(bridge.chat).toHaveBeenCalledWith(
      'session-1',
      '记录一笔午餐支出30元',
      [{ role: 'user', content: 'previous' }],
      expect.stringContaining('[Web chat browser mode: backend]'),
      'default',
      expect.objectContaining({
        capabilities: {
          browser: { mode: 'backend' },
          computer_use: { enabled: false },
        },
      }),
    )
    expect(bridge.contextEstimate.mock.calls[0][2]).toContain('system prompt')
    expect(bridge.contextEstimate.mock.calls[0][2]).toContain('[Reins Finance workflow]')
    expect(bridge.contextEstimate.mock.calls[0][2]).toContain('finance_record_transaction')
    expect(bridge.contextEstimate.mock.calls[0][2]).toContain('X-Hermes-Profile')
    expect(state.contextTokens).toBe(12345)
    expect(emit).toHaveBeenCalledWith('usage.updated', expect.objectContaining({
      inputTokens: 11,
      outputTokens: 7,
      contextTokens: 12345,
    }))
    expect(emit).toHaveBeenCalledWith('run.completed', expect.objectContaining({
      inputTokens: 11,
      outputTokens: 7,
      contextTokens: 12345,
    }))
  })

  it('prepares a connected visible browser before bridge chat runs', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    prepareBrowserForRunMock.mockResolvedValueOnce({
      connected: true,
      cdpUrl: 'http://127.0.0.1:9222',
      browser: 'Chrome',
      profile: 'default',
      managed: true,
    })
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 42,
        fixed_context_tokens: 24,
        message_count: 1,
        tool_count: 4,
        system_prompt_chars: 13,
        capabilities_key: 'browser:connected|computer:on',
      }),
      streamOutput: vi.fn(async function* () {
        yield { run_id: 'run-1', done: true, status: 'completed', output: 'done' }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      {
        input: 'visit example.com',
        session_id: 'session-1',
        capabilities: {
          browser: { mode: 'connected' },
          computer_use: { enabled: true },
        },
      },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(prepareBrowserForRunMock).toHaveBeenCalledWith('default', {
      browser: { mode: 'connected' },
      computer_use: { enabled: true },
    })
    expect(bridge.contextEstimate).toHaveBeenCalledWith(
      'session-1',
      [],
      expect.stringContaining('[Web chat browser mode: connected]'),
      'default',
      expect.objectContaining({
        capabilities: {
          browser: { mode: 'connected' },
          computer_use: { enabled: true },
        },
      }),
    )
    expect(bridge.chat).toHaveBeenCalledWith(
      'session-1',
      'visit example.com',
      expect.any(Array),
      expect.stringContaining('visible connected browser'),
      'default',
      expect.objectContaining({
        capabilities: {
          browser: { mode: 'connected' },
          computer_use: { enabled: true },
        },
      }),
    )
  })

  it('injects the deterministic WeCom gateway workflow for WeCom requests', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 12345,
        fixed_context_tokens: 12327,
        message_count: 2,
        tool_count: 5,
        system_prompt_chars: 13,
        capabilities_key: 'browser:backend|computer:on',
      }),
      streamOutput: vi.fn(async function* () {
        yield { run_id: 'run-1', done: true, status: 'completed', output: 'drafted' }
      }),
    } as any
    recordBridgeToolStartedMock.mockImplementationOnce((_state: any, _sessionId: string, _runMarker: string, toolName: string, args: Record<string, unknown> | undefined, rawToolCallId: unknown) => ({
      id: String(rawToolCallId || 'wecom-workflow-tool'),
      name: toolName,
      arguments: JSON.stringify(args || {}),
    }))
    recordBridgeToolCompletedMock.mockImplementationOnce((_state: any, _sessionId: string, _runMarker: string, _toolName: string, ev: Record<string, unknown>) => ({
      id: String(ev.tool_call_id || 'wecom-workflow-tool'),
      output: String(ev.result || ''),
      duration: 0.4,
    }))

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      {
        input: 'Handle a WeCom ticket notification and record it',
        session_id: 'session-1',
        capabilities: {
          browser: { mode: 'backend' },
          computer_use: { enabled: false },
        },
      },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(prepareBrowserForRunMock).toHaveBeenCalledWith('default', {
      browser: { mode: 'backend' },
      computer_use: { enabled: false },
    })
    expect(bridge.contextEstimate).toHaveBeenCalledWith(
      'session-1',
      [],
      expect.stringContaining('[Reins WeCom work-order workflow requested]'),
      'default',
      expect.objectContaining({
        capabilities: {
          browser: { mode: 'backend' },
          computer_use: { enabled: false },
        },
      }),
    )
    expect(bridge.chat).toHaveBeenCalledWith(
      'session-1',
      'Handle a WeCom ticket notification and record it',
      expect.any(Array),
      expect.stringContaining('parse that text into JSON'),
      'default',
      expect.objectContaining({
        capabilities: {
          browser: { mode: 'backend' },
          computer_use: { enabled: false },
        },
      }),
    )
    expect(emit).toHaveBeenCalledWith('tool.started', expect.objectContaining({
      tool: 'wecom_workflow',
      preview: expect.stringContaining('Receive WeCom ticket notification text'),
      arguments: expect.stringContaining('desktop_computer_use'),
    }))
    expect(emit).toHaveBeenCalledWith('tool.completed', expect.objectContaining({
      tool: 'wecom_workflow',
      output: expect.stringContaining('WeChat Customer Service callbacks'),
    }))
    expect(emit).toHaveBeenCalledWith('agent.event', expect.objectContaining({
      kind: 'workflow',
      text: expect.stringContaining('Reins WeCom work-order workflow enabled'),
    }))
  })

  it('creates chat documents with Reins Office without starting the agent bridge', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const document = {
      id: 'office-1',
      title: 'Maintenance Report',
      kind: 'docx',
      path: '/tmp/maintenance-report.docx',
      file_name: 'maintenance-report.docx',
    }
    const officeRequest = { operation: 'create', format: 'docx' }
    resolveOfficeChatRequestMock.mockReturnValueOnce(officeRequest)
    runOfficeChatRequestMock.mockImplementationOnce(async (...args: any[]) => {
      args[3]?.({
        stage: 'content_generation',
        percent: 18,
        message_zh: 'Reins 正在整理内容',
        message_en: 'Reins is planning the content',
      })
      return {
        handled: true,
        message: 'Office document created successfully.',
        exit_code: 0,
        document,
        operation: 'create',
      }
    })
    addMessageMock.mockReturnValue(42)
    const bridge = {
      chat: vi.fn(),
      contextEstimate: vi.fn(),
      streamOutput: vi.fn(),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      {
        input: 'create a maintenance report document',
        work_tool: 'document',
        office_skill_id: 'community-work-summary',
        session_id: 'session-1',
      },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(resolveOfficeChatRequestMock).toHaveBeenCalledWith(
      'create a maintenance report document',
      'document',
      state.messages,
    )
    expect(runOfficeChatRequestMock).toHaveBeenCalledWith(
      'create a maintenance report document',
      officeRequest,
      'community-work-summary',
      expect.any(Function),
      expect.any(AbortSignal),
    )
    expect(bridge.chat).not.toHaveBeenCalled()
    expect(buildCompressedHistoryMock).not.toHaveBeenCalled()
    expect(recordBridgeToolStartedMock).toHaveBeenCalledWith(
      state,
      'session-1',
      expect.stringMatching(/^cli_run_/),
      'reins_office_create',
      {
        prompt: 'create a maintenance report document',
        format: 'docx',
        skill_id: 'community-work-summary',
      },
      expect.stringMatching(/^office_tool_/),
    )
    expect(recordBridgeToolCompletedMock).toHaveBeenCalledWith(
      state,
      'session-1',
      expect.stringMatching(/^cli_run_/),
      'reins_office_create',
      expect.objectContaining({
        tool_call_id: 'office-tool-1',
        is_error: false,
      }),
    )
    expect(emit).toHaveBeenCalledWith('tool.started', expect.objectContaining({
      tool: 'reins_office_create',
      preview: expect.stringContaining('Reins Office'),
    }))
    expect(emit).toHaveBeenCalledWith('tool.started', expect.objectContaining({
      progress_stage: 'content_generation',
      progress_percent: 18,
      preview: 'Reins is planning the content · 18%',
    }))
    expect(emit).toHaveBeenCalledWith('agent.event', expect.objectContaining({
      kind: 'workflow',
      stage: 'content_generation',
      percent: 18,
    }))
    expect(emit).toHaveBeenCalledWith('tool.completed', expect.objectContaining({
      tool: 'reins_office_create',
      output: '{"ok":true}',
      office_document: document,
    }))
    expect(addMessageMock).toHaveBeenCalledWith(expect.objectContaining({
      role: 'assistant',
      content: expect.stringContaining('Office document created successfully'),
    }))
    expect(emit).toHaveBeenCalledWith('message.delta', expect.objectContaining({
      delta: expect.not.stringContaining('/tmp/maintenance-report.docx'),
    }))
    expect(emit).toHaveBeenCalledWith('message.delta', expect.objectContaining({
      delta: expect.not.stringContaining('Path:'),
    }))
    expect(emit).toHaveBeenCalledWith('run.completed', expect.objectContaining({
      result: { office_document: document },
      output: expect.not.stringContaining('/tmp/maintenance-report.docx'),
    }))
    expect(state.isWorking).toBe(false)
  })

  it('revises the existing chat document without starting the general agent bridge', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const document = {
      id: 'office-1',
      title: 'Maintenance Report',
      kind: 'docx',
      path: '/tmp/maintenance-report.docx',
      file_name: 'maintenance-report.docx',
    }
    const state = makeState()
    const persistedOfficeMessage = {
      role: 'tool',
      tool_name: 'create_office_document',
      content: JSON.stringify({ ok: true, office_document: document }),
    }
    const sessionMap = new Map([['session-1', state]])
    const officeRequest = { operation: 'revise', document }
    hasOfficeRevisionIntentMock.mockReturnValueOnce(true)
    getLatestToolMessageMock.mockReturnValueOnce(persistedOfficeMessage)
    resolveOfficeChatRequestMock
      .mockReturnValueOnce(null)
      .mockReturnValueOnce(officeRequest)
    runOfficeChatRequestMock.mockResolvedValueOnce({
      handled: true,
      message: 'Office document updated successfully.',
      exit_code: 0,
      document: { ...document, revision_count: 1 },
      operation: 'revise',
    })
    recordBridgeToolStartedMock.mockReturnValueOnce({
      id: 'office-tool-revise-1',
      name: 'reins_office_revise',
      arguments: JSON.stringify({ document_id: document.id }),
    })
    recordBridgeToolCompletedMock.mockReturnValueOnce({
      id: 'office-tool-revise-1',
      output: JSON.stringify({ ok: true }),
      duration: 0.2,
    })
    addMessageMock.mockReturnValue(43)
    const bridge = {
      chat: vi.fn(),
      contextEstimate: vi.fn(),
      streamOutput: vi.fn(),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      {
        input: 'make the title bolder and use a modern color palette',
        session_id: 'session-1',
      },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(runOfficeChatRequestMock).toHaveBeenCalledWith(
      'make the title bolder and use a modern color palette',
      officeRequest,
      undefined,
      expect.any(Function),
      expect.any(AbortSignal),
    )
    expect(getLatestToolMessageMock).toHaveBeenCalledWith(
      'session-1',
      expect.arrayContaining(['reins_office_create', 'create_office_document']),
    )
    expect(bridge.chat).not.toHaveBeenCalled()
    expect(recordBridgeToolStartedMock).toHaveBeenCalledWith(
      state,
      'session-1',
      expect.stringMatching(/^cli_run_/),
      'reins_office_revise',
      {
        document_id: 'office-1',
        file_name: 'maintenance-report.docx',
        instruction: 'make the title bolder and use a modern color palette',
      },
      expect.stringMatching(/^office_tool_/),
    )
    expect(emit).toHaveBeenCalledWith('tool.started', expect.objectContaining({
      tool: 'reins_office_revise',
      preview: expect.stringContaining('existing document'),
    }))
  })

  it('revises the latest indexed workspace document when chat history has no Office tool', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const document = {
      id: 'workspace-office-1',
      title: '社区防汛方案',
      kind: 'docx',
      path: '/Users/mei/Documents/Reins Workspace/Word/社区防汛方案.docx',
      file_name: '社区防汛方案.docx',
    }
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const officeRequest = { operation: 'revise', document }
    hasOfficeRevisionIntentMock.mockReturnValueOnce(true)
    getLatestToolMessageMock.mockReturnValueOnce(null)
    listOfficeDocumentsMock.mockResolvedValueOnce([document])
    resolveIndexedOfficeRevisionDocumentMock.mockReturnValueOnce(document)
    runOfficeChatRequestMock.mockResolvedValueOnce({
      handled: true,
      message: 'Office document updated successfully.',
      exit_code: 0,
      document: { ...document, revision_count: 1 },
      operation: 'revise',
    })
    recordBridgeToolStartedMock.mockReturnValueOnce({
      id: 'office-tool-workspace-revise-1',
      name: 'reins_office_revise',
      arguments: JSON.stringify({ document_id: document.id }),
    })
    recordBridgeToolCompletedMock.mockReturnValueOnce({
      id: 'office-tool-workspace-revise-1',
      output: JSON.stringify({ ok: true }),
      duration: 0.2,
    })
    const bridge = {
      chat: vi.fn(),
      contextEstimate: vi.fn(),
      streamOutput: vi.fn(),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      {
        input: '请修改这个文档的标题颜色，并增加更多细节',
        session_id: 'session-1',
      },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(listOfficeDocumentsMock).toHaveBeenCalledWith(100)
    expect(resolveIndexedOfficeRevisionDocumentMock).toHaveBeenCalledWith(
      '请修改这个文档的标题颜色，并增加更多细节',
      [document],
      undefined,
    )
    expect(runOfficeChatRequestMock).toHaveBeenCalledWith(
      '请修改这个文档的标题颜色，并增加更多细节',
      officeRequest,
      undefined,
      expect.any(Function),
      expect.any(AbortSignal),
    )
    expect(bridge.chat).not.toHaveBeenCalled()
  })

  it('asks for clarification as a normal assistant reply when revision planning needs more detail', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const document = {
      id: 'office-needs-detail',
      title: '社区工作方案',
      kind: 'docx',
      path: '/Users/mei/Documents/Reins Workspace/Word/社区工作方案.docx',
      file_name: '社区工作方案.docx',
    }
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const officeRequest = { operation: 'revise', document }
    resolveOfficeChatRequestMock.mockReturnValueOnce(officeRequest)
    runOfficeChatRequestMock.mockRejectedValueOnce(
      new Error('Reins did not return a valid structured Word revision'),
    )
    friendlyOfficeOperationErrorMock.mockReturnValueOnce({
      code: 'content_generation_failed',
      technical_detail: 'Reins did not return a valid structured Word revision',
    })
    shouldAskForOfficeClarificationMock.mockReturnValueOnce(true)
    recordBridgeToolStartedMock.mockReturnValueOnce({
      id: 'office-tool-clarify-1',
      name: 'reins_office_revise',
      arguments: JSON.stringify({ document_id: document.id }),
    })
    recordBridgeToolCompletedMock.mockReturnValueOnce({
      id: 'office-tool-clarify-1',
      output: JSON.stringify({ ok: false, needs_clarification: true, office_document: document }),
      duration: 0.2,
    })
    const bridge = {
      chat: vi.fn(),
      contextEstimate: vi.fn(),
      streamOutput: vi.fn(),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: '修改这个文件', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(officeClarificationPromptMock).toHaveBeenCalledWith(officeRequest, '修改这个文件')
    expect(emit).toHaveBeenCalledWith('message.delta', expect.objectContaining({
      delta: '请告诉我要修改的部分、目标内容和需要保留的内容。',
    }))
    expect(emit).toHaveBeenCalledWith('run.completed', expect.objectContaining({
      result: expect.objectContaining({
        office_document: document,
        needs_clarification: true,
      }),
    }))
    expect(emit).not.toHaveBeenCalledWith('run.failed', expect.anything())
    expect(recordBridgeToolCompletedMock).toHaveBeenCalledWith(
      state,
      'session-1',
      expect.stringMatching(/^cli_run_/),
      'reins_office_revise',
      expect.objectContaining({
        is_error: false,
        result: expect.stringContaining('"needs_clarification": true'),
      }),
    )
    expect(bridge.chat).not.toHaveBeenCalled()
  })

  it('evaluates active goals after a successful bridge run and queues continuation prompts', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const dequeueNextQueuedRun = vi.fn()
    addMessageMock.mockReturnValue(42)
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 12345,
        message_count: 2,
        tool_count: 4,
        system_prompt_chars: 13,
      }),
      goalEvaluate: vi.fn().mockResolvedValue({
        handled: true,
        should_continue: true,
        continuation_prompt: '[Continuing toward your standing goal]\nGoal: fix tests',
        message: '↻ Continuing toward goal (1/20): tests still fail',
        verdict: 'continue',
      }),
      streamOutput: vi.fn(async function* () {
        yield {
          run_id: 'run-1',
          done: true,
          status: 'completed',
          output: 'not finished',
          result: { final_response: 'not finished' },
        }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      {
        input: 'hello',
        session_id: 'session-1',
        model_groups: [{ provider: 'openai', models: ['gpt-test'] }],
      },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      dequeueNextQueuedRun,
    )

    expect(bridge.goalEvaluate).toHaveBeenCalledWith('session-1', 'not finished', 'default')
    expect(addMessageMock).toHaveBeenCalledWith(expect.objectContaining({
      session_id: 'session-1',
      role: 'command',
      content: '↻ Continuing toward goal (1/20): tests still fail',
    }))
    expect(emit).toHaveBeenCalledWith('session.command', expect.objectContaining({
      command: 'goal',
      action: 'continue',
      message: '↻ Continuing toward goal (1/20): tests still fail',
    }))
    expect(state.queue).toEqual([expect.objectContaining({
      input: '[Continuing toward your standing goal]\nGoal: fix tests',
      displayInput: null,
      storageMessage: '[Continuing toward your standing goal]\nGoal: fix tests',
      model: 'gpt-test',
      provider: 'openai',
      model_groups: [{ provider: 'openai', models: ['gpt-test'] }],
      goalContinuation: true,
    })])
    expect(dequeueNextQueuedRun).toHaveBeenCalledWith(socket, 'session-1')
  })

  it('skips hidden goal continuation runs without pausing when the judge is unavailable', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const dequeueNextQueuedRun = vi.fn()
    addMessageMock.mockReturnValue(43)
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      command: vi.fn(),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 12345,
        message_count: 2,
        tool_count: 4,
        system_prompt_chars: 13,
      }),
      goalEvaluate: vi.fn().mockResolvedValue({
        handled: true,
        should_continue: true,
        continuation_prompt: '[Continuing toward your standing goal]\nGoal: fix tests',
        message: '↻ Continuing toward goal (1/20): no auxiliary client configured',
        verdict: 'continue',
        reason: 'no auxiliary client configured',
      }),
      streamOutput: vi.fn(async function* () {
        yield {
          run_id: 'run-1',
          done: true,
          status: 'completed',
          output: 'done',
          result: { final_response: 'done' },
        }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: 'hello', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      dequeueNextQueuedRun,
    )

    expect(bridge.command).not.toHaveBeenCalled()
    expect(state.queue).toEqual([])
    expect(dequeueNextQueuedRun).not.toHaveBeenCalled()
    expect(emit).toHaveBeenCalledWith('session.command', expect.objectContaining({
      command: 'goal',
      action: 'judge_unavailable',
      message: 'Goal judge is not configured; automatic goal continuation was skipped. The goal remains active, but Hermes cannot mark it done automatically.',
    }))
  })

  it('uses cached fixed context instead of bridge estimate when available', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn(),
      streamOutput: vi.fn(async function* () {
        yield {
          run_id: 'run-1',
          done: false,
          status: 'running',
          events: [{
            event: 'bridge.context.ready',
            fixed_context_tokens: 20_000,
            system_prompt_tokens: 3_000,
            tool_tokens: 17_000,
            capabilities_key: 'browser:backend|computer:off',
          }],
        }
        yield { run_id: 'run-1', done: true, status: 'completed', output: 'done' }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: 'hello', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(bridge.contextEstimate).not.toHaveBeenCalled()
    expect(updateMessageContextTokenUsageMock).toHaveBeenCalledWith(
      'session-1',
      state,
      expect.any(Function),
      18,
      { inputTokens: 11, outputTokens: 7 },
    )
    expect(state.contextTokens).toBe(20_018)
    expect(emit).toHaveBeenCalledWith('run.completed', expect.objectContaining({
      contextTokens: 20_018,
    }))
  })

  it('keeps bridge context ready updates on the snapshot-aware token baseline', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    calcAndUpdateUsageMock.mockResolvedValue({ inputTokens: 28_000, outputTokens: 0 })
    buildDbHistoryMock.mockResolvedValue([
      { role: 'user', content: 'very large old context' },
      { role: 'assistant', content: 'large old response' },
      { role: 'user', content: 'hello' },
    ])
    buildSnapshotAwareHistoryMock.mockResolvedValue([
      { role: 'user', content: '[Previous context summary]\n\nsmall summary' },
      { role: 'user', content: 'hello' },
    ])
    estimateUsageTokensFromMessagesMock.mockImplementation((messages: any[]) => {
      if (messages?.[0]?.content?.includes('small summary')) {
        return { inputTokens: 9_000, outputTokens: 0 }
      }
      return { inputTokens: 28_000, outputTokens: 0 }
    })
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn(),
      streamOutput: vi.fn(async function* () {
        yield {
          run_id: 'run-1',
          done: false,
          status: 'running',
          events: [{
            event: 'bridge.context.ready',
            fixed_context_tokens: 10_000,
            system_prompt_tokens: 2_000,
            tool_tokens: 8_000,
          }],
        }
        yield { run_id: 'run-1', done: true, status: 'completed', output: 'done' }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: 'hello', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(updateMessageContextTokenUsageMock).toHaveBeenCalledWith(
      'session-1',
      state,
      expect.any(Function),
      9_000,
      { inputTokens: 28_000, outputTokens: 0 },
    )
    expect(updateMessageContextTokenUsageMock).not.toHaveBeenCalledWith(
      'session-1',
      state,
      expect.any(Function),
      28_000,
      { inputTokens: 28_000, outputTokens: 0 },
    )
    expect(state.contextTokens).toBe(19_000)
    expect(emit).toHaveBeenCalledWith('run.completed', expect.objectContaining({
      contextTokens: 19_000,
    }))
  })

  it('persists pending tool marker text before a bridge run completes', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const persistedContent: string[] = []
    flushBridgePendingToDbMock.mockImplementation((targetState: any) => {
      persistedContent.push(targetState.bridgePendingAssistantContent || '')
      targetState.bridgePendingAssistantContent = ''
    })
    ensureOpenBridgeAssistantMessageMock.mockImplementation((targetState: any, sessionId: string, runMarker: string) => {
      let message = [...targetState.messages].reverse().find((m: any) => m.runMarker === runMarker && m.role === 'assistant' && m.finish_reason == null)
      if (!message) {
        message = {
          id: targetState.messages.length + 1,
          session_id: sessionId,
          runMarker,
          role: 'assistant',
          content: '',
          timestamp: Math.floor(Date.now() / 1000),
        }
        targetState.messages.push(message)
      }
      return message
    })
    const sessionMap = new Map([['session-1', state]])
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 12345,
        message_count: 2,
        tool_count: 4,
        system_prompt_chars: 13,
      }),
      streamOutput: vi.fn(async function* () {
        yield { run_id: 'run-1', done: false, status: 'running', delta: 'Text [Call', events: [] }
        yield { run_id: 'run-1', done: true, status: 'completed', output: '', events: [] }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: 'hello', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(persistedContent).toContain('Text [Call')
    expect(emit).toHaveBeenCalledWith('message.delta', expect.objectContaining({
      delta: 'Text ',
      output: 'Text ',
    }))
    expect(emit).toHaveBeenCalledWith('message.delta', expect.objectContaining({
      delta: '[Call',
      output: 'Text [Call',
    }))
    expect(emit).toHaveBeenCalledWith('run.completed', expect.objectContaining({
      output: 'Text [Call',
    }))
  })

  it('persists the visible plan command instead of the expanded skill prompt', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 12345,
        message_count: 2,
        tool_count: 4,
        system_prompt_chars: 13,
      }),
      streamOutput: vi.fn(async function* () {
        yield { run_id: 'run-1', done: true, status: 'completed', output: 'planned' }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      {
        input: '[IMPORTANT: expanded plan skill prompt]',
        display_input: '/plan build the feature',
        display_role: 'command',
        storage_message: '/plan build the feature',
        session_id: 'session-1',
      },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(state.messages.find((message: any) => message.role === 'command')).toEqual(expect.objectContaining({
      role: 'command',
      content: '/plan build the feature',
    }))
    expect(addMessageMock).toHaveBeenCalledWith(expect.objectContaining({
      role: 'command',
      content: '/plan build the feature',
    }))
    expect(addMessageMock).not.toHaveBeenCalledWith(expect.objectContaining({
      role: 'user',
      content: '[IMPORTANT: expanded plan skill prompt]',
    }))
    expect(bridge.chat).toHaveBeenCalledWith(
      'session-1',
      '[IMPORTANT: expanded plan skill prompt]',
      expect.any(Array),
      expect.any(String),
      'default',
      expect.objectContaining({ storage_message: '/plan build the feature' }),
    )
  })

  it('refreshes full context tokens when a bridge run fails', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const bridge = {
      chat: vi.fn().mockRejectedValue(new Error('bridge timeout')),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 54321,
        fixed_context_tokens: 54303,
        message_count: 1,
        tool_count: 4,
        system_prompt_chars: 13,
      }),
      streamOutput: vi.fn(),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: 'hello', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(state.contextTokens).toBe(54321)
    expect(emit).toHaveBeenCalledWith('usage.updated', expect.objectContaining({
      inputTokens: 11,
      outputTokens: 7,
      contextTokens: 54321,
    }))
    expect(emit).toHaveBeenCalledWith('run.failed', expect.objectContaining({
      error: 'bridge timeout',
      inputTokens: 11,
      outputTokens: 7,
      contextTokens: 54321,
    }))
  })

  it('emits bridge lifecycle status events so retries are visible', async () => {
    const emit = vi.fn()
    const nsp = makeNamespace(emit)
    const socket = makeSocket()
    const state = makeState()
    const sessionMap = new Map([['session-1', state]])
    const bridge = {
      chat: vi.fn().mockResolvedValue({ run_id: 'run-1', status: 'started' }),
      contextEstimate: vi.fn().mockResolvedValue({
        token_count: 12345,
        message_count: 2,
        tool_count: 4,
        system_prompt_chars: 13,
      }),
      streamOutput: vi.fn(async function* () {
        yield {
          run_id: 'run-1',
          done: false,
          status: 'running',
          events: [
            { event: 'status', kind: 'lifecycle', text: 'Retrying in 3.0s (attempt 1/3)...' },
          ],
        }
        yield { run_id: 'run-1', done: true, status: 'completed', output: 'done' }
      }),
    } as any

    const { handleBridgeRun } = await import('../../packages/server/src/services/hermes/run-chat/handle-bridge-run')
    await handleBridgeRun(
      nsp,
      socket,
      { input: 'hello', session_id: 'session-1' },
      'default',
      sessionMap,
      bridge,
      false,
      vi.fn(),
      vi.fn(),
    )

    expect(replaceStateMock).toHaveBeenCalledWith(sessionMap, 'session-1', 'agent.event', expect.objectContaining({
      event: 'agent.event',
      kind: 'lifecycle',
      text: 'Retrying in 3.0s (attempt 1/3)...',
    }))
    expect(emit).toHaveBeenCalledWith('agent.event', expect.objectContaining({
      event: 'agent.event',
      kind: 'lifecycle',
      text: 'Retrying in 3.0s (attempt 1/3)...',
    }))
  })
})
