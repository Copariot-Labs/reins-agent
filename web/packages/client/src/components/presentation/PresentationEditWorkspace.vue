<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NInput,
  NProgress,
  NRadioButton,
  NRadioGroup,
  NSlider,
  NTooltip,
  useMessage,
} from 'naive-ui'

import {
  createPresentationChat,
  createPresentationSession,
  fetchPresentationSession,
  fetchPresentationSessions,
  presentationDownloadUrl,
  presentationPreviewUrl,
  sendPresentationSessionMessage,
  type PresentationAction,
  type PresentationEditOutputFormat,
  type PresentationSession,
  type PresentationSessionTurn,
  type PresentationStyle,
} from '@/api/hermes/presentations'

const { locale } = useI18n()
const message = useMessage()

const copy = computed(() => locale.value.toLowerCase().startsWith('zh') ? {
  decks: '演示文稿', newChat: '新建对话', upload: '上传 PPTX 或 PDF',
  emptyDecks: '还没有演示文稿', newPresentation: '新演示文稿',
  promptSource: '由对话创建', pdfSource: 'PDF 资料',
  revision: '当前版本', original: '原稿', new: '创建', modify: '修改', restyle: '换风格', convert: '转换',
  createPlaceholder: '描述你需要的演示文稿，包括主题、受众、重点内容和期望的语气。',
  pdfPlaceholder: '说明要如何根据这份 PDF 创建演示文稿。',
  modifyPlaceholder: '继续提出修改，例如：精简第 3 页，并把结论改得更有说服力。',
  restylePlaceholder: '例如：改成克制的企业风格，保持所有内容、版式和素材不变。',
  convertPlaceholder: '例如：转换为便于浏览器演示和分享的版本。',
  send: '发送', sending: '处理中', style: '风格', html: '网页演示', pdf: 'PDF',
  title: '标题（可选）', audience: '受众（可选）', slides: '页数', ratio: '比例',
  titlePlaceholder: '由内容自动提炼', audiencePlaceholder: '董事会、客户、产品团队',
  download: '下载', preview: '预览', noMessages: '你需要一份什么样的演示文稿？',
  pdfReady: '这份 PDF 将作为新演示文稿的内容资料。', pptxReady: '发送第一条修改指令。',
  uploadFailed: '文件上传失败', loadFailed: '无法读取演示文稿会话',
  sent: '已开始处理', sendFailed: '无法提交指令', invalidFile: '请选择 PPTX 或 PDF 文件',
  previewBlocked: '浏览器阻止了预览窗口',
  statuses: {
    created: '排队中', analyzing: '正在分析', planning: '正在规划', plan_ready: '分析完成',
    applying: '正在应用', rendering: '正在渲染', qa: '正在质检', completed: '已完成', failed: '失败',
  },
} : {
  decks: 'Presentations', newChat: 'New chat', upload: 'Upload PPTX or PDF',
  emptyDecks: 'No presentations yet', newPresentation: 'New presentation',
  promptSource: 'Created from chat', pdfSource: 'PDF source',
  revision: 'Current revision', original: 'Original', new: 'Create', modify: 'Modify', restyle: 'Restyle', convert: 'Convert',
  createPlaceholder: 'Describe the presentation you need, including its topic, audience, key points, and desired tone.',
  pdfPlaceholder: 'Describe the presentation to build from this PDF.',
  modifyPlaceholder: 'Continue with a change, such as: Tighten slide 3 and make the conclusion more persuasive.',
  restylePlaceholder: 'Apply a restrained corporate theme while keeping every slide, object, and asset intact.',
  convertPlaceholder: 'Create a browser-friendly version for presenting and sharing.',
  send: 'Send', sending: 'Working', style: 'Style', html: 'Web presentation', pdf: 'PDF',
  title: 'Title (optional)', audience: 'Audience (optional)', slides: 'Slides', ratio: 'Ratio',
  titlePlaceholder: 'Derived from the brief', audiencePlaceholder: 'Board, customers, product team',
  download: 'Download', preview: 'Preview', noMessages: 'What presentation do you need?',
  pdfReady: 'This PDF will be used as source material for a new presentation.', pptxReady: 'Send the first editing instruction.',
  uploadFailed: 'Could not upload the file', loadFailed: 'Could not load presentation sessions',
  sent: 'Presentation operation started', sendFailed: 'Could not submit the instruction',
  invalidFile: 'Choose a PPTX or PDF file', previewBlocked: 'The browser blocked the preview window',
  statuses: {
    created: 'Queued', analyzing: 'Analyzing', planning: 'Planning', plan_ready: 'Analysis ready',
    applying: 'Applying', rendering: 'Rendering', qa: 'Quality check', completed: 'Completed', failed: 'Failed',
  },
})

const styleOptions: Array<{ value: PresentationStyle, color: string }> = [
  { value: 'modern', color: '#1d4ed8' },
  { value: 'tech', color: '#22d3ee' },
  { value: 'corporate', color: '#008f86' },
  { value: 'creative', color: '#f04438' },
  { value: 'minimal', color: '#111111' },
  { value: 'dark', color: '#ff6b35' },
]

const sessions = ref<PresentationSession[]>([])
const selectedSessionId = ref<string | null>(null)
const operation = ref<Exclude<PresentationAction, 'new'>>('modify')
const instruction = ref('')
const title = ref('')
const audience = ref('')
const slideCount = ref(8)
const aspectRatio = ref<'16:9' | '4:3'>('16:9')
const style = ref<PresentationStyle>('modern')
const convertFormat = ref<'html' | 'pdf'>('html')
const loading = ref(false)
const uploading = ref(false)
const sending = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const chatHistory = ref<HTMLElement | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const currentSession = computed(() => (
  sessions.value.find(session => session.session_id === selectedSessionId.value) || null
))
const needsInitialDeck = computed(() => !currentSession.value?.deck_ready)
const activeTurn = computed(() => currentSession.value?.turns.find(turn => !isTerminal(turn)) || null)
const outputFormat = computed<PresentationEditOutputFormat>(() => (
  operation.value === 'convert' ? convertFormat.value : 'pptx'
))
const placeholder = computed(() => {
  if (needsInitialDeck.value) {
    return currentSession.value?.source_type === 'pdf' ? copy.value.pdfPlaceholder : copy.value.createPlaceholder
  }
  if (operation.value === 'restyle') return copy.value.restylePlaceholder
  if (operation.value === 'convert') return copy.value.convertPlaceholder
  return copy.value.modifyPlaceholder
})
const canSend = computed(() => (
  instruction.value.trim().length >= (currentSession.value ? 3 : 12)
  && !sending.value
  && !activeTurn.value
))

function isTerminal(turn: PresentationSessionTurn): boolean {
  return turn.job.status === 'completed' || turn.job.status === 'failed'
}

function statusLabel(status: string): string {
  return (copy.value.statuses as Record<string, string>)[status] || status
}

function actionLabel(action: PresentationAction): string {
  return copy.value[action]
}

function upsertSession(session: PresentationSession) {
  const index = sessions.value.findIndex(value => value.session_id === session.session_id)
  if (index >= 0) sessions.value.splice(index, 1, session)
  else sessions.value.unshift(session)
}

async function scrollToLatest() {
  await nextTick()
  if (chatHistory.value) chatHistory.value.scrollTop = chatHistory.value.scrollHeight
}

async function loadSessions(showError = true) {
  loading.value = true
  try {
    sessions.value = await fetchPresentationSessions(30)
    if (selectedSessionId.value && !sessions.value.some(value => value.session_id === selectedSessionId.value)) {
      selectedSessionId.value = null
    }
  } catch (error: any) {
    if (showError) message.error(error?.message || copy.value.loadFailed)
  } finally {
    loading.value = false
  }
  schedulePoll()
}

async function selectSession(sessionId: string) {
  selectedSessionId.value = sessionId
  resetComposerOptions()
  try {
    upsertSession(await fetchPresentationSession(sessionId))
    await scrollToLatest()
  } catch (error: any) {
    message.error(error?.message || copy.value.loadFailed)
  }
}

function resetComposerOptions() {
  title.value = ''
  audience.value = ''
  slideCount.value = 8
  aspectRatio.value = '16:9'
  style.value = 'modern'
  operation.value = 'modify'
  convertFormat.value = 'html'
}

function startNewChat() {
  selectedSessionId.value = null
  instruction.value = ''
  resetComposerOptions()
}

function chooseFile() {
  fileInput.value?.click()
}

async function handleFile(file: File | undefined) {
  if (!file || !/\.(pptx|pdf)$/i.test(file.name)) {
    message.warning(copy.value.invalidFile)
    return
  }
  uploading.value = true
  try {
    const session = await createPresentationSession(file)
    upsertSession(session)
    selectedSessionId.value = session.session_id
    instruction.value = ''
    resetComposerOptions()
    await scrollToLatest()
  } catch (error: any) {
    message.error(error?.message || copy.value.uploadFailed)
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function handleSend() {
  if (!canSend.value) return
  sending.value = true
  const prompt = instruction.value.trim()
  try {
    let updated: PresentationSession
    if (!currentSession.value) {
      updated = await createPresentationChat({
        prompt,
        title: title.value.trim() || undefined,
        audience: audience.value.trim() || undefined,
        language: locale.value,
        slide_count: slideCount.value,
        style: style.value,
        engine: 'auto',
        aspect_ratio: aspectRatio.value,
        run_qa: true,
      })
      selectedSessionId.value = updated.session_id
    } else {
      updated = await sendPresentationSessionMessage(currentSession.value.session_id, {
        action: needsInitialDeck.value ? 'new' : operation.value,
        instruction: prompt,
        title: title.value.trim() || undefined,
        audience: audience.value.trim() || undefined,
        slide_count: slideCount.value,
        aspect_ratio: aspectRatio.value,
        style: style.value,
        output_format: needsInitialDeck.value ? 'pptx' : outputFormat.value,
        language: locale.value,
        run_qa: true,
      })
    }
    upsertSession(updated)
    instruction.value = ''
    message.success(copy.value.sent)
    await scrollToLatest()
    schedulePoll()
  } catch (error: any) {
    message.error(error?.message || copy.value.sendFailed)
  } finally {
    sending.value = false
  }
}

function download(turn: PresentationSessionTurn) {
  const anchor = document.createElement('a')
  anchor.href = presentationDownloadUrl(turn.job.job_id)
  anchor.download = turn.job.output_file_name || 'presentation'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}

function preview(turn: PresentationSessionTurn) {
  const opened = window.open(presentationPreviewUrl(turn.job.job_id), '_blank', 'noopener,noreferrer')
  if (!opened) message.warning(copy.value.previewBlocked)
}

function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer)
  const activeSessions = sessions.value.filter(session => session.turns.some(turn => !isTerminal(turn))).slice(0, 5)
  if (!activeSessions.length) return
  pollTimer = setTimeout(async () => {
    const updates = await Promise.all(activeSessions.map(async session => {
      try { return await fetchPresentationSession(session.session_id) } catch { return null }
    }))
    updates.forEach(session => { if (session) upsertSession(session) })
    await scrollToLatest()
    schedulePoll()
  }, 1800)
}

onMounted(() => loadSessions(false))
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>

<template>
  <section class="editor-shell">
    <aside class="deck-sidebar">
      <div class="sidebar-heading">
        <strong>{{ copy.decks }}</strong>
        <div class="sidebar-actions">
          <NTooltip>
            <template #trigger>
              <NButton quaternary circle :aria-label="copy.newChat" @click="startNewChat">
                <span class="button-symbol" aria-hidden="true">+</span>
              </NButton>
            </template>
            {{ copy.newChat }}
          </NTooltip>
          <NTooltip>
            <template #trigger>
              <NButton quaternary circle :loading="uploading" :aria-label="copy.upload" @click="chooseFile">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="20" height="20">
                  <g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"></path>
                    <path d="M7 9l5-5l5 5"></path>
                    <path d="M12 4v12"></path>
                  </g>
                </svg>
              </NButton>
            </template>
            {{ copy.upload }}
          </NTooltip>
        </div>
        <input
          ref="fileInput"
          class="visually-hidden"
          type="file"
          accept=".pptx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation"
          @change="handleFile(($event.target as HTMLInputElement).files?.[0])"
        >
      </div>

      <div class="deck-list">
        <button
          type="button"
          class="deck-item new-deck"
          :class="{ active: !selectedSessionId }"
          @click="startNewChat"
        >
          <span class="deck-icon new-icon" aria-hidden="true">+</span>
          <span class="deck-copy"><strong>{{ copy.newPresentation }}</strong></span>
        </button>
        <button
          v-for="session in sessions"
          :key="session.session_id"
          type="button"
          class="deck-item"
          :class="{ active: selectedSessionId === session.session_id }"
          @click="selectSession(session.session_id)"
        >
          <span class="deck-icon" :class="{ pdf: session.source_type === 'pdf' }" aria-hidden="true">
            {{ session.source_type === 'pdf' ? 'PDF' : 'P' }}
          </span>
          <span class="deck-copy">
            <strong>{{ session.name }}</strong>
            <small>{{ copy.revision }} {{ session.active_revision || copy.original }}</small>
          </span>
        </button>
        <p v-if="!sessions.length && !loading" class="sidebar-empty">{{ copy.emptyDecks }}</p>
      </div>
    </aside>

    <div class="chat-pane">
      <header class="chat-header">
        <div>
          <h2>{{ currentSession?.name || copy.newPresentation }}</h2>
          <p v-if="currentSession">
            {{ currentSession.source_file_name || copy.promptSource }}
          </p>
        </div>
        <span v-if="currentSession" class="revision-label">
          {{ copy.revision }} {{ currentSession.active_revision || copy.original }}
        </span>
      </header>

      <div ref="chatHistory" class="chat-history" aria-live="polite">
        <div v-if="!currentSession?.turns.length" class="conversation-empty">
          <strong>{{ currentSession?.source_type === 'pdf' ? copy.pdfReady : currentSession ? copy.pptxReady : copy.noMessages }}</strong>
        </div>
        <div v-for="turn in currentSession?.turns || []" :key="turn.turn" class="turn">
          <div class="user-message">
            <span class="operation-label">{{ actionLabel(turn.action) }}</span>
            <p>{{ turn.instruction }}</p>
          </div>
          <div class="assistant-message" :class="{ failed: turn.job.status === 'failed' }">
            <div class="response-heading">
              <strong>{{ statusLabel(turn.job.status) }}</strong>
              <span>v{{ turn.parent_revision }} → {{ turn.advances_deck ? `v${turn.turn}` : turn.output_format.toUpperCase() }}</span>
            </div>
            <NProgress
              v-if="!isTerminal(turn)"
              type="line"
              :percentage="turn.job.progress"
              :height="6"
              :border-radius="2"
              :show-indicator="false"
            />
            <p>{{ turn.job.error || turn.job.phase }}</p>
            <div v-if="turn.job.has_output" class="turn-actions">
              <NButton v-if="turn.job.preview_available" secondary size="small" @click="preview(turn)">
                {{ copy.preview }}
              </NButton>
              <NButton type="primary" size="small" @click="download(turn)">{{ copy.download }}</NButton>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-composer">
        <div v-if="needsInitialDeck" class="creation-controls">
          <div class="creation-text-fields">
            <NInput v-model:value="title" size="small" :placeholder="copy.title" :maxlength="180" />
            <NInput v-model:value="audience" size="small" :placeholder="copy.audience" :maxlength="300" />
          </div>
          <div class="creation-options">
            <label class="slide-control">
              <span>{{ copy.slides }} <strong>{{ slideCount }}</strong></span>
              <NSlider v-model:value="slideCount" :min="3" :max="20" :step="1" />
            </label>
            <label class="ratio-control">
              <span>{{ copy.ratio }}</span>
              <NRadioGroup v-model:value="aspectRatio" size="small">
                <NRadioButton value="16:9">16:9</NRadioButton>
                <NRadioButton value="4:3">4:3</NRadioButton>
              </NRadioGroup>
            </label>
          </div>
        </div>

        <div v-else class="operation-row">
          <NRadioGroup v-model:value="operation" size="small">
            <NRadioButton value="modify">{{ copy.modify }}</NRadioButton>
            <NRadioButton value="restyle">{{ copy.restyle }}</NRadioButton>
            <NRadioButton value="convert">{{ copy.convert }}</NRadioButton>
          </NRadioGroup>
          <NRadioGroup v-if="operation === 'convert'" v-model:value="convertFormat" size="small">
            <NRadioButton value="html">{{ copy.html }}</NRadioButton>
            <NRadioButton value="pdf">{{ copy.pdf }}</NRadioButton>
          </NRadioGroup>
        </div>

        <div v-if="needsInitialDeck || operation === 'restyle'" class="style-row" :aria-label="copy.style">
          <button
            v-for="option in styleOptions"
            :key="option.value"
            type="button"
            class="style-swatch"
            :class="{ active: style === option.value }"
            :aria-label="option.value"
            :title="option.value"
            @click="style = option.value"
          >
            <span :style="{ backgroundColor: option.color }"></span>
          </button>
        </div>

        <div class="input-row">
          <NInput
            v-model:value="instruction"
            type="textarea"
            :placeholder="placeholder"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :maxlength="needsInitialDeck ? 30000 : 10000"
            @keydown.meta.enter.prevent="handleSend"
            @keydown.ctrl.enter.prevent="handleSend"
          />
          <NTooltip>
            <template #trigger>
              <NButton
                type="primary"
                circle
                size="large"
                :loading="sending"
                :disabled="!canSend"
                :aria-label="copy.send"
                @click="handleSend"
              >
                <span class="button-symbol send-symbol" aria-hidden="true">↑</span>
              </NButton>
            </template>
            {{ sending ? copy.sending : copy.send }}
          </NTooltip>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.editor-shell {
  // min-height: 680px;
  height: calc(100vh - 120px);
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid $border-color;
  border-radius: 6px;
  background: $bg-card;
}
.deck-sidebar { min-width: 0; border-right: 1px solid $border-color; background: $bg-secondary; }
.sidebar-heading, .chat-header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 14px 0 18px;
  border-bottom: 1px solid $border-color;
}
.sidebar-heading strong { font-size: 13px; }
.sidebar-actions { display: flex; gap: 2px; }
.button-symbol { display: block; font-size: 22px; font-weight: 400; line-height: 1; }
.upload-symbol, .send-symbol { font-size: 20px; font-weight: 700; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.deck-list { max-height: calc(100vh - 190px); overflow-y: auto; padding: 8px; }
.deck-item {
  width: 100%;
  min-height: 54px;
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 4px;
  padding: 8px 10px;
  border: 0;
  border-radius: 4px;
  color: $text-secondary;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.deck-item:hover, .deck-item.active { color: $text-primary; background: $bg-card-hover; }
.deck-item.active { box-shadow: inset 3px 0 0 $accent-primary; }
.deck-icon {
  width: 28px;
  height: 34px;
  display: grid;
  place-items: center;
  flex: 0 0 28px;
  border-radius: 3px;
  color: white;
  background: #e34b35;
  font-size: 11px;
  font-weight: 800;
}
.deck-icon.pdf { background: #b42318; font-size: 8px; }
.deck-icon.new-icon { color: $text-secondary; background: $bg-input; font-size: 20px; font-weight: 400; }
.deck-copy { min-width: 0; display: grid; gap: 3px; }
.deck-copy strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.deck-copy small { color: $text-muted; font-size: 10px; }
.sidebar-empty { margin: 20px 10px; color: $text-muted; font-size: 11px; text-align: center; }
.chat-pane { min-width: 0; min-height: 680px; display: flex; flex-direction: column; }
.chat-header { padding: 0 20px; }
.chat-header h2 { margin: 0; max-width: min(62vw, 680px); overflow: hidden; font-size: 15px; letter-spacing: 0; text-overflow: ellipsis; white-space: nowrap; }
.chat-header p { margin: 3px 0 0; color: $text-muted; font-size: 10px; }
.revision-label { color: $text-muted; font-size: 11px; white-space: nowrap; }
.chat-history {
  flex: 1 1 auto;
  // min-height: 350px;
  max-height: calc(100vh - 390px);
  overflow-y: auto;
  padding: 26px clamp(18px, 5vw, 66px);
  background: $bg-primary;
}
.conversation-empty { height: 100%; display: grid; place-items: center; color: $text-muted; text-align: center; }
.conversation-empty strong { max-width: 480px; color: $text-secondary; font-size: 16px; font-weight: 600; line-height: 1.5; }
.turn { display: grid; gap: 10px; margin-bottom: 26px; }
.user-message { width: min(76%, 620px); justify-self: end; }
.user-message p {
  margin: 5px 0 0;
  padding: 11px 14px;
  border-radius: 6px 6px 2px 6px;
  color: $text-secondary;
  background: $bg-card;
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.operation-label { display: block; color: $text-muted; font-size: 10px; text-align: right; }
.assistant-message { width: min(82%, 680px); padding: 13px 15px; border-left: 3px solid $success; color: $text-secondary; background: $bg-card; }
.assistant-message.failed { border-left-color: $error; }
.assistant-message > p { margin: 10px 0 0; font-size: 12px; line-height: 1.5; }
.response-heading { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 10px; }
.response-heading strong { color: $text-primary; font-size: 12px; }
.response-heading span { color: $text-muted; font-size: 10px; }
.turn-actions { display: flex; gap: 8px; margin-top: 12px; }
.chat-composer { flex: 0 0 auto; padding: 12px 18px 18px; border-top: 1px solid $border-color; }
.creation-controls { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(310px, 1.25fr); gap: 16px; margin-bottom: 8px; }
.creation-text-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; align-content: start; }
.creation-options { display: grid; grid-template-columns: minmax(160px, 1fr) auto; align-items: start; gap: 18px; }
.slide-control, .ratio-control { min-width: 0; display: grid; gap: 3px; color: $text-muted; font-size: 10px; }
.slide-control strong { color: $text-primary; }
.operation-row { min-height: 34px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.style-row { display: flex; gap: 7px; margin: 8px 0 2px; }
.style-swatch {
  width: 27px;
  height: 25px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid $border-color;
  border-radius: 3px;
  background: $bg-input;
  cursor: pointer;
}
.style-swatch span { width: 13px; height: 13px; border-radius: 2px; }
.style-swatch.active { border-color: $accent-primary; box-shadow: 0 0 0 1px $accent-primary; }
.input-row { display: grid; grid-template-columns: minmax(0, 1fr) 42px; align-items: end; gap: 10px; margin-top: 10px; }

@media (max-width: 960px) {
  .creation-controls { grid-template-columns: 1fr; }
}
@media (max-width: 820px) {
  .editor-shell { grid-template-columns: 1fr; }
  .deck-sidebar { border-right: 0; border-bottom: 1px solid $border-color; }
  .deck-list { max-height: none; display: flex; overflow-x: auto; }
  .deck-item { min-width: 200px; }
  .new-deck { min-width: 150px; }
  .chat-history { max-height: none; }
}
@media (max-width: $breakpoint-mobile) {
  .editor-shell { min-height: calc(100vh - 130px); border-width: 1px 0 0; border-radius: 0; }
  .chat-pane { min-height: 620px; }
  .chat-header h2 { max-width: 58vw; }
  .chat-history { padding: 20px 14px; }
  .user-message, .assistant-message { width: 92%; }
  .operation-row { align-items: flex-start; flex-direction: column; }
  .creation-text-fields, .creation-options { grid-template-columns: 1fr; }
  .chat-composer { padding: 12px 14px 16px; }
}
</style>
