<script setup lang="ts">
import type { Attachment } from '@/stores/hermes/chat'
import { useChatStore } from '@/stores/hermes/chat'
import { useChatCapabilitiesStore } from '@/stores/hermes/chat-capabilities'
import { useAppStore } from '@/stores/hermes/app'
import { useProfilesStore } from '@/stores/hermes/profiles'
import { fetchContextLength } from '@/api/hermes/sessions'
import { setModelContext } from '@/api/hermes/model-context'
import {
  connectVisibleBrowser,
  disconnectVisibleBrowser,
  type VisibleBrowserStatus,
} from '@/api/hermes/browser'
import { fetchComputerUseDoctor, fetchComputerUseStatus, type ComputerUseCheck } from '@/api/hermes/computer-use'
import { fetchOfficeSkills, type OfficeFormat, type OfficeSkill } from '@/api/reins/office'
import { NButton, NTooltip, NModal, NInputNumber, useMessage } from 'naive-ui'
import { computed, ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToolTraceVisibility } from '@/composables/useToolTraceVisibility'
import {
  getWorkSuggestions,
  getOfficeFormatOptions,
  getWorkToolOptions,
  routedWorkTool,
  shouldShowNewChatSuggestions,
  type WorkSuggestion,
  type WorkTool,
  type OfficeWorkTool,
} from './work-suggestions'

const chatStore = useChatStore()
const capabilitiesStore = useChatCapabilitiesStore()
const appStore = useAppStore()
const profilesStore = useProfilesStore()
const { t, locale } = useI18n()
const emit = defineEmits<{
  sessionStarted: [sessionId: string]
}>()
const message = useMessage()
const { toolTraceVisible, toggleToolTraceVisible } = useToolTraceVisibility()
const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const commandDropdownRef = ref<HTMLDivElement>()
const fileInputRef = ref<HTMLInputElement>()
const attachments = ref<Attachment[]>([])
const isDragging = ref(false)
const dragCounter = ref(0)
const isComposing = ref(false)
const isConnectingVisibleBrowser = ref(false)
const isCheckingComputerUse = ref(false)
const visibleBrowserStatus = ref<VisibleBrowserStatus | null>(null)
const computerUseStatus = ref<ComputerUseCheck | null>(null)
const computerUseDoctor = ref<ComputerUseCheck | null>(null)
const suggestionsDismissedForSession = ref(false)
const officeSkills = ref<OfficeSkill[]>([])
const officeSkillsLoaded = ref(false)
const officeSkillsLoading = ref(false)
const officeSkillsError = ref('')

const selectedWorkTool = ref<WorkTool>('general')
const selectedOfficeFormat = ref<OfficeWorkTool | null>(null)
const selectedOfficeSkillId = ref('')
const isChinese = computed(() => locale.value.toLowerCase().startsWith('zh'))
const workToolOptions = computed(() => getWorkToolOptions(isChinese.value))
const officeFormatOptions = computed(() => getOfficeFormatOptions(isChinese.value))
const selectedWorkToolOption = computed(() =>
  (selectedOfficeFormat.value
    ? officeFormatOptions.value.find(option => option.id === selectedOfficeFormat.value)
    : workToolOptions.value.find(option => option.id === selectedWorkTool.value)),
)
const selectedOfficeSkill = computed(() =>
  officeSkills.value.find(skill => skill.id === selectedOfficeSkillId.value) || null,
)
const officeSkillsCopy = computed(() => isChinese.value
  ? {
      loading: '正在读取 Office 技能',
      empty: '此格式暂无可用技能',
      failed: 'Office 技能加载失败',
      retry: '重试',
    }
  : {
      loading: 'Loading Office skills',
      empty: 'No skills are available for this format',
      failed: 'Failed to load Office skills',
      retry: 'Retry',
    })
const officeSkillSuggestions = computed<WorkSuggestion[]>(() => {
  const format = officeFormatForWorkTool(selectedOfficeFormat.value)
  if (!format) return []
  return officeSkills.value
    .filter(skill => skill.format === format)
    .map(skill => {
      const placeholder = isChinese.value ? skill.placeholder_zh : skill.placeholder_en
      return {
        id: skill.id,
        label: isChinese.value ? skill.label_zh : skill.label_en,
        description: isChinese.value ? skill.description_zh : skill.description_en,
        prompt: placeholder.replace(isChinese.value ? /^例如[：:]\s*/ : /^Example:\s*/i, ''),
        officeSkillId: skill.id,
      }
    })
})
const workSuggestions = computed(() =>
  selectedOfficeFormat.value
    ? officeSkillSuggestions.value
    : getWorkSuggestions(selectedWorkTool.value, isChinese.value),
)
const showNewChatSuggestions = computed(() => {
  if (chatStore.isLoadingSessions || suggestionsDismissedForSession.value) return false
  const session = chatStore.activeSession
  return shouldShowNewChatSuggestions({
    hasSession: Boolean(session),
    title: session?.title,
    messageCount: session?.messageCount,
    messageTotal: session?.messageTotal,
    loadedMessageCount: session?.loadedMessageCount,
    visibleMessageCount: chatStore.messages.length,
    isLoadingMessages: chatStore.isLoadingMessages,
  })
})
const composerPlaceholder = computed(() => {
  const selected = selectedWorkToolOption.value
  if (!selected) return t('chat.inputPlaceholder')
  return isChinese.value
    ? `告诉 Reins 你想用${selected.label}完成什么…`
    : `Tell Reins what you want to accomplish with ${selected.label.toLowerCase()}...`
})

function selectWorkTool(tool: WorkTool) {
  const nextTool = selectedWorkTool.value === tool ? 'general' : tool
  selectedWorkTool.value = nextTool
  selectedOfficeFormat.value = null
  selectedOfficeSkillId.value = ''
  if (nextTool === 'document') void ensureOfficeSkillsLoaded()
  if (nextTool === 'research' && capabilitiesStore.browserMode === 'off') {
    capabilitiesStore.browserMode = 'backend'
  }
  if (nextTool === 'browser') {
    capabilitiesStore.browserMode = 'connected'
  }
  nextTick(() => textareaRef.value?.focus())
}

function officeFormatForWorkTool(tool: OfficeWorkTool | null): OfficeFormat | null {
  if (tool === 'document') return 'docx'
  if (tool === 'spreadsheet') return 'xlsx'
  if (tool === 'slides') return 'pptx'
  return null
}

async function ensureOfficeSkillsLoaded(force = false) {
  if (officeSkillsLoading.value || (officeSkillsLoaded.value && !force)) return
  officeSkillsLoading.value = true
  officeSkillsError.value = ''
  try {
    const response = await fetchOfficeSkills()
    officeSkills.value = response.skills
    officeSkillsLoaded.value = true
  } catch (error) {
    officeSkillsError.value = String((error as { message?: unknown })?.message || officeSkillsCopy.value.failed)
  } finally {
    officeSkillsLoading.value = false
  }
}

function selectOfficeFormat(tool: OfficeWorkTool) {
  selectedOfficeFormat.value = tool
  selectedWorkTool.value = tool
  selectedOfficeSkillId.value = ''
  void ensureOfficeSkillsLoaded()
  nextTick(() => textareaRef.value?.focus())
}

function backSuggestionLevel() {
  if (selectedOfficeFormat.value) {
    selectedOfficeFormat.value = null
    selectedOfficeSkillId.value = ''
    selectedWorkTool.value = 'document'
    return
  }
  clearWorkTool()
}

function clearWorkTool() {
  selectedWorkTool.value = 'general'
  selectedOfficeFormat.value = null
  selectedOfficeSkillId.value = ''
  nextTick(() => textareaRef.value?.focus())
}

function applyWorkSuggestion(suggestion: WorkSuggestion) {
  selectedOfficeSkillId.value = suggestion.officeSkillId || ''
  inputText.value = suggestion.prompt
  nextTick(() => {
    const el = textareaRef.value
    if (!el) return
    el.focus()
    el.setSelectionRange(inputText.value.length, inputText.value.length)
    handleInput({ target: el } as unknown as Event)
  })
}

watch(
  () => chatStore.activeSessionId,
  () => {
    selectedWorkTool.value = 'general'
    selectedOfficeFormat.value = null
    selectedOfficeSkillId.value = ''
    suggestionsDismissedForSession.value = false
  },
)

async function ensureVisibleBrowserConnected(showToast = true) {
  if (isConnectingVisibleBrowser.value) return
  isConnectingVisibleBrowser.value = true
  try {
    const status = await connectVisibleBrowser()
    visibleBrowserStatus.value = status
    if (showToast && status.connected) {
      message.success('Visible browser connected')
    } else if (showToast) {
      message.error(status.error || 'Visible browser is not connected')
    }
  } catch (err: any) {
    if (showToast) message.error(`Visible browser connect failed: ${err?.message || err}`)
  } finally {
    isConnectingVisibleBrowser.value = false
  }
}

async function ensureVisibleBrowserDisconnected(showToast = false) {
  if (isConnectingVisibleBrowser.value) return
  isConnectingVisibleBrowser.value = true
  try {
    visibleBrowserStatus.value = await disconnectVisibleBrowser()
  } catch (err: any) {
    if (showToast) message.error(`Visible browser disconnect failed: ${err?.message || err}`)
  } finally {
    isConnectingVisibleBrowser.value = false
  }
}

async function refreshComputerUseStatus(showToast = false) {
  if (isCheckingComputerUse.value) return
  isCheckingComputerUse.value = true
  try {
    const status = await fetchComputerUseStatus()
    computerUseStatus.value = status
    if (!status.ok) {
      computerUseDoctor.value = await fetchComputerUseDoctor().catch(() => null)
    }
    if (showToast) {
      if (status.ok) message.success('Computer use ready')
      else message.warning(status.error || status.stderr || 'Computer use needs attention')
    }
  } catch (err: any) {
    if (showToast) message.error(`Computer use check failed: ${err?.message || err}`)
    computerUseStatus.value = {
      ok: false,
      command: [],
      profile: capabilitiesStore.profileName,
      stdout: '',
      stderr: '',
      error: err?.message || String(err),
    }
  } finally {
    isCheckingComputerUse.value = false
  }
}

watch(
  () => capabilitiesStore.browserMode,
  (mode) => {
    if (mode === 'connected') void ensureVisibleBrowserConnected()
    else void ensureVisibleBrowserDisconnected(true)
  },
)

watch(
  () => capabilitiesStore.computerUseEnabled,
  (enabled) => {
    if (enabled) void refreshComputerUseStatus(true)
  },
)

// const visibleBrowserStatusLabel = computed(() => {
//   if (isConnectingVisibleBrowser.value) return 'Checking visible browser...'
//   const status = visibleBrowserStatus.value
//   if (!status) return 'Visible browser status unknown'
//   if (status.connected) return `Visible browser connected${status.browser ? `: ${status.browser}` : ''}`
//   return status.error ? `Visible browser disconnected: ${status.error}` : 'Visible browser disconnected'
// })

// const visibleBrowserStatusClass = computed(() => {
//   if (isConnectingVisibleBrowser.value) return 'checking'
//   if (!visibleBrowserStatus.value) return 'unknown'
//   return visibleBrowserStatus.value.connected ? 'ready' : 'error'
// })

const computerUseStatusLabel = computed(() => {
  if (isCheckingComputerUse.value) return 'Checking computer use...'
  const status = computerUseStatus.value
  if (!capabilitiesStore.computerUseEnabled) return 'Computer use disabled'
  if (!status) return 'Computer use status unknown'
  if (status.ok) return 'Computer use ready'
  return status.error || status.stderr || 'Computer use needs attention'
})

const computerUseStatusClass = computed(() => {
  if (isCheckingComputerUse.value) return 'checking'
  if (!capabilitiesStore.computerUseEnabled) return 'unknown'
  if (!computerUseStatus.value) return 'unknown'
  return computerUseStatus.value.ok ? 'ready' : 'error'
})

const bridgeCommands = computed(() => [
  { name: 'usage', args: '', description: t('chat.slashCommands.usage') },
  { name: 'status', args: '', description: t('chat.slashCommands.status') },
  { name: 'abort', args: '', description: t('chat.slashCommands.abort') },
  { name: 'queue', args: t('chat.slashCommandArgs.message'), description: t('chat.slashCommands.queue') },
  { name: 'plan', args: t('chat.slashCommandArgs.text'), description: t('chat.slashCommands.plan') },
  { name: 'goal', args: t('chat.slashCommandArgs.text'), description: t('chat.slashCommands.goal') },
  { name: 'goal', args: 'status', insertText: 'goal status', description: t('chat.slashCommands.goalStatus') },
  { name: 'goal', args: 'pause', insertText: 'goal pause', description: t('chat.slashCommands.goalPause') },
  { name: 'goal', args: 'resume', insertText: 'goal resume', description: t('chat.slashCommands.goalResume') },
  { name: 'goal', args: 'done', insertText: 'goal done', description: t('chat.slashCommands.goalDone') },
  { name: 'goal', args: 'clear', insertText: 'goal clear', description: t('chat.slashCommands.goalClear') },
  { name: 'subgoal', args: t('chat.slashCommandArgs.text'), description: t('chat.slashCommands.subgoal') },
  { name: 'clear', args: '', description: t('chat.slashCommands.clear') },
  { name: 'clear', args: '--history', insertText: 'clear --history', description: t('chat.slashCommands.clearHistory') },
  { name: 'title', args: t('chat.slashCommandArgs.title'), description: t('chat.slashCommands.title') },
  { name: 'compress', args: '', description: t('chat.slashCommands.compress') },
  { name: 'steer', args: t('chat.slashCommandArgs.text'), description: t('chat.slashCommands.steer') },
  { name: 'destroy', args: '', description: t('chat.slashCommands.destroy') },
])

const slashActive = ref(false)
const slashQuery = ref('')
const slashActiveIndex = ref(0)
const isBridgeSession = computed(() => chatStore.activeSession?.source === 'cli')
const filteredBridgeCommands = computed(() => {
  const query = slashQuery.value.toLowerCase()
  return bridgeCommands.value.filter(command =>
    command.name.includes(query) || command.insertText?.includes(query),
  )
})

// 自定义高度拖拽
const textareaHeight = ref<number | null>(null) // null = auto

function startResize(e: MouseEvent) {
  e.preventDefault()
  const el = textareaRef.value
  if (!el) return
  // 如果当前是 auto，用实际 clientHeight 作为起始值
  const startHeight = el.clientHeight
  const startY = e.clientY

  function onMouseMove(e: MouseEvent) {
    const deltaY = e.clientY - startY
    // 往上拖 (deltaY < 0) → 高度增加
    const newHeight = startHeight - deltaY
    textareaHeight.value = Math.max(20, Math.min(400, Math.round(newHeight)))
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

// 自动播放语音开关
const autoPlaySpeech = ref(false)

// 从 localStorage 读取设置
onMounted(() => {
  const saved = localStorage.getItem('autoPlaySpeech')
  if (saved !== null) {
    autoPlaySpeech.value = saved === 'true'
    // 同步到 chat store
    chatStore.setAutoPlaySpeech(autoPlaySpeech.value)
  }
  if (capabilitiesStore.browserMode === 'connected') {
    void ensureVisibleBrowserConnected(false)
  } else {
    void ensureVisibleBrowserDisconnected()
  }
  if (capabilitiesStore.computerUseEnabled) void refreshComputerUseStatus()
})

// 监听变化并保存
watch(autoPlaySpeech, (value) => {
  localStorage.setItem('autoPlaySpeech', String(value))
  // 通知 chat store
  chatStore.setAutoPlaySpeech(value)
})

const canSend = computed(() => inputText.value.trim() || attachments.value.length > 0)

function scrollCommandIntoView() {
  nextTick(() => {
    if (!commandDropdownRef.value) return
    const active = commandDropdownRef.value.querySelector('.active') as HTMLElement | null
    active?.scrollIntoView({ block: 'nearest', behavior: 'instant' })
  })
}

function updateSlashState() {
  if (!isBridgeSession.value) {
    slashActive.value = false
    return
  }
  const el = textareaRef.value
  if (!el) return
  const cursorPos = el.selectionStart
  const beforeCursor = inputText.value.slice(0, cursorPos)
  if (!beforeCursor.startsWith('/') || beforeCursor.includes(' ') || beforeCursor.includes('\n')) {
    slashActive.value = false
    return
  }
  slashQuery.value = beforeCursor.slice(1)
  slashActiveIndex.value = 0
  slashActive.value = filteredBridgeCommands.value.length > 0
}

function selectBridgeCommand(command: { name: string; args: string; insertText?: string }) {
  inputText.value = `/${command.insertText || command.name} `
  slashActive.value = false
  nextTick(() => {
    const el = textareaRef.value
    if (!el) return
    const pos = inputText.value.length
    el.setSelectionRange(pos, pos)
    el.focus()
  })
}

// --- Context info ---

const contextLength = ref(256000)
const FALLBACK_CONTEXT = 256000
let contextLengthLoadedKey = ''
let contextLengthRequestKey = ''
let contextLengthRequest: Promise<void> | null = null

// Context length editing
const showContextEditModal = ref(false)
const editingContextLimit = ref(256000)
const isSavingContextLimit = ref(false)

async function handleEditContextLimit() {
  editingContextLimit.value = contextLength.value
  showContextEditModal.value = true
}

async function saveContextLimit() {
  if (!editingContextLimit.value || editingContextLimit.value <= 0) {
    message.error(t('chat.contextEditInvalid'))
    return
  }

  isSavingContextLimit.value = true
  try {
    const provider = chatStore.activeSession?.provider || appStore.selectedProvider || ''
    const model = chatStore.activeSession?.model || appStore.selectedModel || ''

    if (!provider || !model) {
      message.error(t('chat.contextEditFailed'))
      return
    }

    await setModelContext(provider, model, editingContextLimit.value)
    contextLength.value = editingContextLimit.value
    contextLengthLoadedKey = currentContextLengthKey()
    showContextEditModal.value = false
    message.success(t('chat.contextEditSuccess'))
  } catch (err: any) {
    message.error(`${t('chat.contextEditFailed')}: ${err.message || ''}`)
  } finally {
    isSavingContextLimit.value = false
  }
}

function currentContextLengthParams() {
  const activeSession = chatStore.activeSession
  return {
    profile: activeSession?.profile || profilesStore.activeProfileName || undefined,
    provider: activeSession?.provider || undefined,
    model: activeSession?.model || undefined,
  }
}

function currentContextLengthKey() {
  const params = currentContextLengthParams()
  return `${params.profile || ''}|${params.provider || ''}|${params.model || ''}`
}

async function loadContextLength() {
  const key = currentContextLengthKey()
  if (key === contextLengthLoadedKey) return
  if (key === contextLengthRequestKey && contextLengthRequest) return contextLengthRequest

  contextLengthRequestKey = key
  contextLengthRequest = (async () => {
    const params = currentContextLengthParams()
    try {
      const value = await fetchContextLength(params.profile, params.provider, params.model)
      if (currentContextLengthKey() !== key) return
      contextLength.value = value
      contextLengthLoadedKey = key
    } catch {
      if (currentContextLengthKey() !== key) return
      contextLength.value = FALLBACK_CONTEXT
      contextLengthLoadedKey = key
    } finally {
      if (contextLengthRequestKey === key) {
        contextLengthRequest = null
        contextLengthRequestKey = ''
      }
    }
  })()
  return contextLengthRequest
}

onMounted(loadContextLength)
watch(
  () => [
    profilesStore.activeProfileName,
    appStore.selectedProvider,
    appStore.selectedModel,
    chatStore.activeSession?.id,
    chatStore.activeSession?.profile,
    chatStore.activeSession?.provider,
    chatStore.activeSession?.model,
  ],
  loadContextLength,
  { flush: 'post' },
)

const totalTokens = computed(() => {
  const context = chatStore.activeSession?.contextTokens
  if (typeof context === 'number' && Number.isFinite(context) && context > 0) return context
  const input = chatStore.activeSession?.inputTokens ?? 0
  const output = chatStore.activeSession?.outputTokens ?? 0
  return input + output
})

const usagePercent = computed(() =>
  Math.min((totalTokens.value / contextLength.value) * 100, 100),
)

function formatTokens(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

// --- File attachment helpers ---

function addFile(file: File) {
  if (attachments.value.find(a => a.name === file.name)) return
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
  const url = URL.createObjectURL(file)
  attachments.value.push({
    id,
    name: file.name,
    type: file.type,
    size: file.size,
    url,
    file,
  })
}

function handleAttachClick() {
  fileInputRef.value?.click()
}

function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  for (const file of input.files) addFile(file)
  input.value = ''
}

// --- Paste image ---

function handlePaste(e: ClipboardEvent) {
  const items = Array.from(e.clipboardData?.items || [])
  const imageItems = items.filter(i => i.type.startsWith('image/'))
  if (!imageItems.length) return
  e.preventDefault()
  for (const item of imageItems) {
    const blob = item.getAsFile()
    if (!blob) continue
    const ext = item.type.split('/')[1] || 'png'
    const file = new File([blob], `pasted-${Date.now()}.${ext}`, { type: item.type })
    addFile(file)
  }
}

// --- Drag and drop ---

function handleDragOver(e: DragEvent) {
  e.preventDefault()
}

function handleDragEnter(e: DragEvent) {
  e.preventDefault()
  if (e.dataTransfer?.types.includes('Files')) {
    dragCounter.value++
    isDragging.value = true
  }
}

function handleDragLeave() {
  dragCounter.value--
  if (dragCounter.value <= 0) {
    dragCounter.value = 0
    isDragging.value = false
  }
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter.value = 0
  isDragging.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  if (!files.length) return
  for (const file of files) addFile(file)
  textareaRef.value?.focus()
}

// --- Send ---

function handleSend() {
  const text = inputText.value.trim()
  if (!text && attachments.value.length === 0) return

  const startsSession = !chatStore.activeSessionId
  suggestionsDismissedForSession.value = true
  chatStore.sendMessage(
    text,
    attachments.value.length > 0 ? attachments.value : undefined,
    {
      workTool: routedWorkTool(selectedWorkTool.value),
      officeSkillId: selectedOfficeSkillId.value || undefined,
    },
  )
  if (startsSession && chatStore.activeSessionId) {
    emit('sessionStarted', chatStore.activeSessionId)
  }
  inputText.value = ''
  attachments.value = []
  selectedWorkTool.value = 'general'
  selectedOfficeFormat.value = null
  selectedOfficeSkillId.value = ''
  slashActive.value = false

  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
}

function handleCompositionStart() {
  isComposing.value = true
}

function handleCompositionEnd() {
  requestAnimationFrame(() => {
    isComposing.value = false
    updateSlashState()
  })
}

function isImeEnter(e: KeyboardEvent): boolean {
  return isComposing.value || e.isComposing || e.keyCode === 229
}

function handleKeydown(e: KeyboardEvent) {
  if (slashActive.value && filteredBridgeCommands.value.length > 0) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      slashActiveIndex.value = (slashActiveIndex.value + 1) % filteredBridgeCommands.value.length
      scrollCommandIntoView()
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      slashActiveIndex.value = (slashActiveIndex.value - 1 + filteredBridgeCommands.value.length) % filteredBridgeCommands.value.length
      scrollCommandIntoView()
      return
    }
    if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      selectBridgeCommand(filteredBridgeCommands.value[slashActiveIndex.value])
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      slashActive.value = false
      return
    }
  }

  if (e.key !== 'Enter' || e.shiftKey) return
  if (isImeEnter(e)) return

  e.preventDefault()
  handleSend()
}

function handleInput(e: Event) {
  const el = e.target as HTMLTextAreaElement
  if (!isComposing.value) updateSlashState()
  // 用户手动拖拽自定义高度时，不覆盖
  if (textareaHeight.value !== null) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 100) + 'px'
}

function handleCommandHover(index: number) {
  slashActiveIndex.value = index
}

function onDocumentMousedown(e: MouseEvent) {
  if (!slashActive.value) return
  const target = e.target as HTMLElement
  if (!target.closest('.slash-command-dropdown') && !target.closest('.input-wrapper')) {
    slashActive.value = false
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onDocumentMousedown)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocumentMousedown)
})

function removeAttachment(id: string) {
  const idx = attachments.value.findIndex(a => a.id === id)
  if (idx !== -1) {
    URL.revokeObjectURL(attachments.value[idx].url)
    attachments.value.splice(idx, 1)
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function isImage(type: string): boolean {
  return type.startsWith('image/')
}
</script>

<template>
  <div class="chat-input-area">
    <div
      v-if="showNewChatSuggestions"
      class="work-tool-strip"
      :class="{ 'suggestion-strip': selectedWorkTool !== 'general' }"
      :aria-label="selectedWorkTool === 'general' ? 'Work tools' : 'Suggested tasks'"
    >
      <template v-if="selectedWorkTool === 'general'">
        <button
          v-for="tool in workToolOptions"
          :key="tool.id"
          type="button"
          class="work-tool-chip"
          @click="selectWorkTool(tool.id)"
        >
          <svg v-if="tool.icon === 'document'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2h9l4 4v16H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M14 2v5h5M8 12h7M8 16h6"/></svg>
          <svg v-else-if="tool.icon === 'spreadsheet'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>
          <svg v-else-if="tool.icon === 'slides'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 22l4-4 4 4M8 8h8M8 12h5"/></svg>
          <svg v-else-if="tool.icon === 'finance'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h15a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12"/><path d="M16 13h5M17 13h.01"/></svg>
          <svg v-else-if="tool.icon === 'work-orders'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 11l2 2 4-4M9 17h6"/></svg>
          <svg v-else-if="tool.icon === 'research'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="10" cy="10" r="6"/><path d="m14.5 14.5 5 5M17 3v4M15 5h4"/></svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>
          <span>{{ tool.label }}</span>
        </button>
      </template>
      <template v-else-if="selectedWorkTool === 'document' && !selectedOfficeFormat">
        <button
          type="button"
          class="suggestion-back"
          :aria-label="isChinese ? '返回工作类型' : 'Back to work types'"
          :title="isChinese ? '返回工作类型' : 'Back to work types'"
          @click="backSuggestionLevel"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <button
          v-for="option in officeFormatOptions"
          :key="option.id"
          type="button"
          class="work-tool-chip office-format-chip"
          @click="selectOfficeFormat(option.id as OfficeWorkTool)"
        >
          <span class="office-format-mark" :class="option.id">
            {{ option.id === 'document' ? 'W' : option.id === 'spreadsheet' ? 'X' : 'P' }}
          </span>
          <span>{{ option.label }}</span>
        </button>
      </template>
      <template v-else-if="selectedOfficeFormat">
        <button
          type="button"
          class="suggestion-back"
          :aria-label="isChinese ? '返回 Office 格式' : 'Back to Office formats'"
          :title="isChinese ? '返回 Office 格式' : 'Back to Office formats'"
          @click="backSuggestionLevel"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <span v-if="officeSkillsLoading" class="suggestion-state">{{ officeSkillsCopy.loading }}</span>
        <button
          v-else-if="officeSkillsError"
          type="button"
          class="suggestion-state error"
          @click="ensureOfficeSkillsLoaded(true)"
        >
          {{ officeSkillsCopy.failed }} · {{ officeSkillsCopy.retry }}
        </button>
        <span v-else-if="!workSuggestions.length" class="suggestion-state">{{ officeSkillsCopy.empty }}</span>
        <button
          v-for="suggestion in workSuggestions"
          v-else
          :key="suggestion.id"
          type="button"
          class="work-suggestion-chip"
          :class="{ active: suggestion.officeSkillId === selectedOfficeSkillId }"
          :title="suggestion.description"
          @click="applyWorkSuggestion(suggestion)"
        >
          <span>{{ suggestion.label }}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m7 7 10 10M9 17h8V9"/></svg>
        </button>
      </template>
      <template v-else>
        <button
          type="button"
          class="suggestion-back"
          :aria-label="isChinese ? '返回工作类型' : 'Back to work types'"
          :title="isChinese ? '返回工作类型' : 'Back to work types'"
          @click="backSuggestionLevel"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <button
          v-for="suggestion in workSuggestions"
          :key="suggestion.id"
          type="button"
          class="work-suggestion-chip"
          @click="applyWorkSuggestion(suggestion)"
        >
          <span>{{ suggestion.label }}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m7 7 10 10M9 17h8V9"/></svg>
        </button>
      </template>
    </div>

    <!-- Attachment previews -->
    <div v-if="attachments.length > 0" class="attachment-previews">
      <div
        v-for="att in attachments"
        :key="att.id"
        class="attachment-preview"
        :class="{ image: isImage(att.type) }"
      >
        <template v-if="isImage(att.type)">
          <img :src="att.url" :alt="att.name" class="attachment-thumb" />
        </template>
        <template v-else>
          <div class="attachment-file">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <span class="file-name">{{ att.name }}</span>
            <span class="file-size">{{ formatSize(att.size) }}</span>
          </div>
        </template>
        <button class="attachment-remove" @click="removeAttachment(att.id)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>

    <div
      class="input-wrapper"
      :class="{ 'drag-over': isDragging }"
      @dragover="handleDragOver"
      @dragenter="handleDragEnter"
      @dragleave="handleDragLeave"
      @drop="handleDrop"
    >
      <input
        ref="fileInputRef"
        type="file"
        multiple
        class="file-input-hidden"
        @change="handleFileChange"
      />
      <div class="resize-handle" @mousedown="startResize"></div>
      <div v-if="selectedWorkToolOption" class="selected-work-tool-row">
        <button type="button" class="selected-work-tool-pill" @click="clearWorkTool">
          <svg v-if="selectedWorkToolOption.icon === 'document'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2h9l4 4v16H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/><path d="M14 2v5h5M8 12h7M8 16h6"/></svg>
          <svg v-else-if="selectedWorkToolOption.icon === 'spreadsheet'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>
          <svg v-else-if="selectedWorkToolOption.icon === 'slides'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 22l4-4 4 4M8 8h8M8 12h5"/></svg>
          <svg v-else-if="selectedWorkToolOption.icon === 'finance'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h15a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h12"/><path d="M16 13h5M17 13h.01"/></svg>
          <svg v-else-if="selectedWorkToolOption.icon === 'work-orders'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M9 11l2 2 4-4M9 17h6"/></svg>
          <svg v-else-if="selectedWorkToolOption.icon === 'research'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="10" cy="10" r="6"/><path d="m14.5 14.5 5 5M17 3v4M15 5h4"/></svg>
          <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>
          <span>{{ selectedWorkToolOption.label }}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m7 7 10 10M17 7 7 17"/></svg>
        </button>
        <span v-if="selectedOfficeSkill" class="selected-office-skill">
          {{ isChinese ? selectedOfficeSkill.label_zh : selectedOfficeSkill.label_en }}
        </span>
      </div>
      <textarea
        ref="textareaRef"
        v-model="inputText"
        class="input-textarea"
        :style="textareaHeight ? { height: textareaHeight + 'px' } : {}"
        :placeholder="composerPlaceholder"
        rows="1"
        @keydown="handleKeydown"
        @compositionstart="handleCompositionStart"
        @compositionend="handleCompositionEnd"
        @input="handleInput"
        @paste="handlePaste"
      ></textarea>
      <Transition name="dropdown-fade">
        <div
          v-if="slashActive && filteredBridgeCommands.length > 0"
          ref="commandDropdownRef"
          class="slash-command-dropdown"
        >
          <div
            v-for="(command, i) in filteredBridgeCommands"
            :key="command.name"
            class="slash-command-item"
            :class="{ active: i === slashActiveIndex }"
            @mousedown.prevent="selectBridgeCommand(command)"
            @mouseenter="handleCommandHover(i)"
          >
            <span class="slash-command-name">/{{ command.name }}</span>
            <span v-if="command.args" class="slash-command-args">{{ command.args }}</span>
            <span class="slash-command-desc">{{ command.description }}</span>
          </div>
        </div>
      </Transition>
      <div class="input-actions">
        <div class="composer-controls">
          <NTooltip trigger="hover">
            <template #trigger>
              <button type="button" class="round-action" @click="handleAttachClick">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M12 5v14M5 12h14" /></svg>
              </button>
            </template>
            {{ t('chat.attachFiles') }}
          </NTooltip>

          <!-- <NTooltip trigger="hover">
            <template #trigger>
              <button type="button" class="composer-mode" @click="selectWorkTool('browser')">
                <span class="connection-dot" :class="visibleBrowserStatusClass" />
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/></svg>
                <span>{{ capabilitiesStore.browserMode === 'connected' ? 'Visible' : capabilitiesStore.browserMode === 'backend' ? 'Research' : 'Browse off' }}</span>
              </button>
            </template>
            {{ visibleBrowserStatusLabel }}
          </NTooltip> -->

          <NTooltip trigger="hover">
            <template #trigger>
              <button
                type="button"
                class="composer-mode"
                :class="{ active: capabilitiesStore.computerUseEnabled }"
                @click="capabilitiesStore.computerUseEnabled = !capabilitiesStore.computerUseEnabled"
              >
                <span class="connection-dot" :class="computerUseStatusClass" />
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
                <span>{{ isChinese ? '桌面' : 'Desktop' }}</span>
              </button>
            </template>
            {{ computerUseStatusLabel }}
          </NTooltip>

          <NTooltip trigger="hover">
            <template #trigger>
              <button type="button" class="round-action" :class="{ active: toolTraceVisible }" @click="toggleToolTraceVisible">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4.5 4.5 0 0 0-5.8 5.8L3.5 17.5a2.1 2.1 0 0 0 3 3l5.4-5.4a4.5 4.5 0 0 0 5.8-5.8l-3 3-3-3 3-3z"/></svg>
              </button>
            </template>
            {{ toolTraceVisible ? t('chat.hideToolCalls') : t('chat.showToolCalls') }}
          </NTooltip>
        </div>

        <span v-if="totalTokens > 0" class="context-info" :class="{ 'context-warning': usagePercent > 80 }">
          {{ formatTokens(totalTokens) }} / <span class="context-limit-editable" @click="handleEditContextLimit">{{ formatTokens(contextLength) }}</span>
        </span>
        <NButton
          v-if="chatStore.isStreaming"
          size="small"
          type="error"
          :disabled="chatStore.isAborting"
          @click="chatStore.stopStreaming()"
        >
          {{ t('chat.stop') }}
        </NButton>
        <NButton
          class="send-action"
          size="small"
          type="primary"
          :disabled="!canSend"
          @click="handleSend"
        >
          <template #icon>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </template>
        </NButton>
      </div>
    </div>

    <!-- Context Length Edit Modal -->
    <NModal
      v-model:show="showContextEditModal"
      :title="t('chat.contextEditTitle')"
      :mask-closable="true"
      preset="card"
      style="width: 400px"
    >
      <div class="context-edit-content">
        <p style="margin-bottom: 16px; color: #666;">
          {{ t('chat.contextEditDesc') }}
        </p>
        <NInputNumber
          v-model:value="editingContextLimit"
          :min="1000"
          :max="10000000"
          :step="1000"
          :show-button="false"
          :placeholder="t('chat.contextEditPlaceholder')"
          style="width: 100%"
        >
          <template #suffix>
            <span style="color: #999;">tokens</span>
          </template>
        </NInputNumber>
        <div style="margin-top: 12px; font-size: 12px; color: #999;">
          {{ t('chat.contextEditHint') }}
        </div>
      </div>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
          <NButton @click="showContextEditModal = false" :disabled="isSavingContextLimit">
            {{ t('chat.contextEditCancel') }}
          </NButton>
          <NButton type="primary" @click="saveContextLimit" :loading="isSavingContextLimit">
            {{ t('chat.contextEditSave') }}
          </NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.chat-input-area {
  width: min(820px, calc(100% - 34px));
  margin: 0 auto;
  padding: 0 0 18px;
  flex-shrink: 0;
}

.work-tool-strip {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 0 10px;
  overflow-x: auto;
  scrollbar-width: none;
}

.work-tool-strip::-webkit-scrollbar { display: none; }

.suggestion-back {
  width: 34px;
  height: 34px;
  display: inline-grid;
  flex: 0 0 34px;
  place-items: center;
  padding: 0;
  border: 1px solid $border-color;
  border-radius: 50%;
  color: $text-secondary;
  background: $bg-card;
  cursor: pointer;
}

.suggestion-back:hover {
  color: $text-primary;
  background: $bg-secondary;
}

.suggestion-state {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  padding: 0 10px;
  border: 0;
  color: $text-muted;
  background: transparent;
  font: inherit;
  font-size: 11px;
}

button.suggestion-state.error {
  color: #b91c1c;
  cursor: pointer;
}

.work-tool-chip {
  height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
  padding: 0 13px;
  border: 1px solid $border-color;
  border-radius: 999px;
  color: $text-secondary;
  background: $bg-card;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: color .15s ease, background .15s ease, border-color .15s ease;
}

.work-tool-chip:hover,
.work-tool-chip.active {
  color: $text-primary;
  border-color: $text-muted;
  background: $bg-secondary;
}

.office-format-chip { padding-left: 7px; }

.office-format-mark {
  width: 22px;
  height: 24px;
  display: grid;
  flex: 0 0 22px;
  place-items: center;
  border-radius: 4px;
  color: #fff;
  background: #2563eb;
  font-size: 9px;
  font-weight: 750;
}

.office-format-mark.spreadsheet { background: #15803d; }
.office-format-mark.slides { background: #c2410c; }

.work-suggestion-chip {
  height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  max-width: 230px;
  padding: 0 15px;
  border: 1px solid transparent;
  border-radius: 999px;
  color: $text-primary;
  background: $bg-secondary;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color .15s ease, background .15s ease, transform .15s ease;
}

.work-suggestion-chip span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.work-suggestion-chip svg {
  flex: 0 0 auto;
  color: $text-muted;
}

.work-suggestion-chip:hover {
  border-color: $text-muted;
  background: $bg-card;
  transform: translateY(-1px);
}

.work-suggestion-chip.active {
  border-color: rgba(var(--accent-primary-rgb), .34);
  background: rgba(var(--accent-primary-rgb), .12);
}

.auto-play-speech-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 0 0 8px;
  border-left: 1px solid $border-light;
  margin-left: 4px;

  .switch-label {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    color: #999999;
    font-size: 12px;

    svg {
      opacity: 1;
    }
  }

  :deep(.n-switch),
  :deep(.n-switch__rail) {
    margin-right: 0;
  }
}

.tool-trace-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #999999;
  width: 24px;
  min-width: 24px;
  height: 22px;
  margin-left: -4px;
  padding: 0;
  background: transparent !important;
  opacity: 1;

  :deep(.n-button__state-border),
  :deep(.n-button__border),
  :deep(.n-button__ripple) {
    display: none;
  }

  .tool-trace-icon {
    display: block;
    flex: 0 0 16px;
    width: 16px;
    height: 16px;
  }

  &.active {
    color: #999999;
    opacity: 1;
  }

  &:hover {
    color: #999999;
    opacity: 1;
  }
}

.capability-control {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding-left: 8px;
  border-left: 1px solid $border-light;
  color: $text-muted;
}

.capability-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 14px;
  width: 14px;
  height: 14px;
}

.connection-dot {
  flex: 0 0 9px;
  width: 9px;
  height: 9px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: $text-muted;
  cursor: pointer;
  opacity: 0.75;

  &.ready {
    background: #34a853;
    opacity: 1;
  }

  &.checking {
    background: #e8a735;
    opacity: 1;
    animation: connectionPulse 1s ease-in-out infinite;
  }

  &.error {
    background: #e85d4a;
    opacity: 1;
  }
}

@keyframes connectionPulse {
  0%,
  100% {
    transform: scale(0.9);
  }

  50% {
    transform: scale(1.2);
  }
}

.capability-select {
  flex: 0 0 auto;

  :deep(.n-base-selection) {
    --n-height: 24px !important;
    min-height: 24px;
    border-radius: $radius-sm;
  }

  :deep(.n-base-selection-label) {
    height: 22px;
    padding: 0 20px 0 7px;
    font-size: 12px;
    line-height: 22px;
  }

  :deep(.n-base-selection-input) {
    height: 22px;
    line-height: 22px;
  }

  :deep(.n-base-selection__state-border),
  :deep(.n-base-selection__border) {
    border-radius: $radius-sm;
  }
}

.browser-select {
  width: 104px;
}

.computer-select {
  width: 124px;
}

.context-info {
  font-size: 11px;
  color: $text-muted;

  &.context-warning {
    color: #e8a735;
  }
}

.context-limit-editable {
  cursor: pointer;
  border-bottom: 1px dashed transparent;
  transition: all 0.2s ease;
  padding: 0 2px;

  &:hover {
    border-bottom-color: $text-muted;
    background: rgba(128, 128, 128, 0.1);
    border-radius: 2px;
  }
}

.context-bar {
  width: 60px;
  height: 4px;
  background: rgba(128, 128, 128, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.context-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(128, 128, 128, 0.3), rgba(128, 128, 128, 0.6));
  border-radius: 2px;
  transition: width 0.3s ease;

  &.context-bar-warn {
    background: linear-gradient(90deg, #c98a1a, #e8a735);
  }

  &.context-bar-danger {
    background: linear-gradient(90deg, #c43a2a, #e85d4a);
  }
}

.attachment-previews {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 0 10px;
}

.attachment-preview {
  position: relative;
  border-radius: $radius-sm;
  overflow: hidden;
  background-color: $bg-secondary;
  border: 1px solid $border-color;

  &.image {
    width: 64px;
    height: 64px;
  }
}

.attachment-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.attachment-file {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 8px 12px;
  min-width: 80px;
  max-width: 140px;
  color: $text-secondary;

  .file-name {
    font-size: 11px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .file-size {
    font-size: 10px;
    color: $text-muted;
  }
}

.attachment-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.5);
  color: var(--text-on-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity $transition-fast;

  .attachment-preview:hover & {
    opacity: 1;
  }
}

.file-input-hidden {
  display: none;
}

.input-wrapper {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  background-color: $bg-input;
  border: 1px solid $border-color;
  border-radius: 18px;
  padding: 15px 16px 12px;
  position: relative;
  box-shadow: 0 12px 38px rgba(0, 0, 0, .07);
  transition: border-color $transition-fast, background-color $transition-fast, box-shadow $transition-fast;

  &:focus-within {
    border-color: $text-muted;
    box-shadow: 0 16px 42px rgba(0, 0, 0, .10);
  }

  .dark & {
    background-color: #333333;
  }
}

.selected-work-tool-row {
  display: flex;
  align-items: center;
  min-height: 30px;
  padding-bottom: 3px;
}

.selected-work-tool-pill {
  height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border: 0;
  border-radius: 999px;
  color: $text-primary;
  background: rgba(var(--accent-primary-rgb), .16);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: background .15s ease;
}

.selected-work-tool-pill:hover {
  background: rgba(var(--accent-primary-rgb), .23);
}

.selected-office-skill {
  min-width: 0;
  overflow: hidden;
  padding-left: 9px;
  color: $text-muted;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resize-handle {
  position: absolute;
  top: -4px;
  left: 0;
  right: 0;
  height: 8px;
  cursor: row-resize;
  z-index: 2;

  &:hover {
    background: rgba($accent-primary, 0.15);
    border-radius: 4px;
  }
}

.input-textarea {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: $text-primary;
  font-family: $font-ui;
  font-size: 15px;
  line-height: 1.5;
  resize: none;
  max-height: 400px;
  min-height: 66px;
  overflow-y: auto;

  &::placeholder {
    color: $text-muted;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  align-items: center;
  min-width: 0;
  padding-top: 7px;
}

.composer-controls {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  overflow-x: auto;
  scrollbar-width: none;
}

.composer-controls::-webkit-scrollbar { display: none; }

.round-action,
.composer-mode {
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  border: 0;
  border-radius: 8px;
  color: $text-muted;
  background: transparent;
  font: inherit;
  cursor: pointer;
}

.round-action { width: 30px; }

.composer-mode {
  gap: 5px;
  padding: 0 8px;
  font-size: 11px;
}

.round-action:hover,
.round-action.active,
.composer-mode:hover,
.composer-mode.active {
  color: $text-primary;
  background: $bg-secondary;
}

.composer-mode .connection-dot {
  width: 7px;
  height: 7px;
  flex-basis: 7px;
}

.send-action {
  min-width: 38px !important;
  width: 38px;
  height: 38px;
  border-radius: 50% !important;
}

.send-action :deep(.n-button__content > span:last-child) {
  display: none;
}

.slash-command-dropdown {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: calc(100% + 8px);
  max-height: 240px;
  overflow-y: auto;
  background: $bg-primary;
  border: 1px solid $border-color;
  border-radius: $radius-sm;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.16);
  z-index: 20;
  padding: 4px;

  .dark & {
    background: #2a2a2a;
  }
}

@media (max-width: $breakpoint-mobile) {
  .chat-input-area { width: calc(100% - 20px); padding-bottom: 10px; }
  .work-tool-chip { height: 32px; padding-inline: 11px; }
  .work-suggestion-chip { height: 34px; padding-inline: 12px; }
  .input-wrapper { border-radius: 15px; padding: 12px; }
  .input-textarea { min-height: 54px; }
  .composer-mode span:last-child { display: none; }
}

.slash-command-item {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: $radius-sm;
  cursor: pointer;
  min-height: 36px;

  &.active,
  &:hover {
    background: rgba(var(--accent-primary-rgb), 0.1);
  }
}

.slash-command-name {
  font-family: $font-code;
  font-size: 13px;
  color: $accent-primary;
  white-space: nowrap;
}

.slash-command-args {
  font-family: $font-code;
  font-size: 12px;
  color: $text-muted;
  white-space: nowrap;
}

.slash-command-desc {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: $text-secondary;
  font-size: 12px;
}

.dropdown-fade-enter-active,
.dropdown-fade-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}

.dropdown-fade-enter-from,
.dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

// Drag-over state
.input-wrapper.drag-over {
  border-color: var(--accent-info);
  border-style: dashed;
  background-color: rgba(var(--accent-info-rgb), 0.04);
}
</style>
