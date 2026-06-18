<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { NButton, NInput, NTag, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import {
  runWorkModeStream,
  type WorkModeEvent,
  type WorkModeName,
} from '@/api/hermes/workmode'

interface WorkStep {
  id: string
  kind: string
  title: string
  worker: string
  description: string
  visible_action?: boolean
  requires_confirmation?: boolean
  expected_artifacts?: string[]
  depends_on?: string[]
  metadata?: Record<string, any>
}

interface FeedItem {
  id: string
  role: 'user' | 'assistant' | 'system'
  title: string
  message: string
  meta: string
  tone: string
}

type RunStatus = 'idle' | 'running' | 'completed' | 'failed'
type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'blocked'
type WorkStage = 'idle' | 'planning' | 'executing' | 'presenting' | 'completed' | 'failed' | 'cancelled'

const { t } = useI18n()
const message = useMessage()

const taskText = ref('Generate a report for the company')
const submittedTask = ref('')
const mode = ref<WorkModeName>('work')
const running = ref(false)
const events = ref<WorkModeEvent[]>([])
const finalSummary = ref<Record<string, any> | null>(null)
const errorText = ref('')
const abortController = ref<AbortController | null>(null)
const feedRef = ref<HTMLElement | null>(null)

const modeOptions = computed(() => [
  { label: t('workmode.modes.work'), value: 'work' as const },
  { label: t('workmode.modes.demo'), value: 'demo' as const },
  { label: t('workmode.modes.headless'), value: 'headless' as const },
])

const exampleTasks = computed(() => [
  // t('workmode.examples.report'),
  t('workmode.examples.browser'),
  t('workmode.examples.wechat'),
])

const statusLabels = computed<Record<RunStatus, string>>(() => ({
  idle: t('workmode.status.idle'),
  running: t('workmode.status.running'),
  completed: t('workmode.status.completed'),
  failed: t('workmode.status.failed'),
}))

const stageLabels = computed<Record<WorkStage, string>>(() => ({
  idle: t('workmode.stage.idle'),
  planning: t('workmode.stage.planning'),
  executing: t('workmode.stage.executing'),
  presenting: t('workmode.stage.presenting'),
  completed: t('workmode.stage.completed'),
  failed: t('workmode.stage.failed'),
  cancelled: t('workmode.stage.cancelled'),
}))

function lastEventOf(types: string[]): WorkModeEvent | null {
  for (let index = events.value.length - 1; index >= 0; index -= 1) {
    if (types.includes(events.value[index].type)) return events.value[index]
  }
  return null
}

const terminalEvent = computed(() => lastEventOf(['task_finished', 'task_failed']))

const status = computed<RunStatus>(() => {
  if (running.value) return 'running'
  if (!terminalEvent.value && events.value.length === 0) return 'idle'
  if (terminalEvent.value?.type === 'task_failed') return 'failed'
  if (finalSummary.value?.status === 'failed') return 'failed'
  return 'completed'
})

const statusTagType = computed(() => {
  if (status.value === 'completed') return 'success'
  if (status.value === 'failed') return 'error'
  if (status.value === 'running') return 'info'
  return 'default'
})

const plan = computed<Record<string, any> | null>(() => {
  const planEvent = lastEventOf(['work.plan.completed'])
  const candidate = planEvent?.data?.plan || finalSummary.value?.plan
  return candidate && typeof candidate === 'object' ? candidate as Record<string, any> : null
})

const steps = computed<WorkStep[]>(() => {
  const rawSteps = plan.value?.steps
  return Array.isArray(rawSteps) ? rawSteps as WorkStep[] : []
})

const routeLabel = computed(() => {
  const summaryRoute = finalSummary.value?.execution_path
  if (typeof summaryRoute === 'string') return summaryRoute
  const startedRoute = events.value.find(event => typeof event.data?.execution_path === 'string')?.data?.execution_path
  return typeof startedRoute === 'string' ? startedRoute : '-'
})

const currentStage = computed<WorkStage>(() => {
  if (events.value.some(event => event.type === 'work.stream.cancelled')) return 'cancelled'
  if (status.value === 'failed') return 'failed'
  if (status.value === 'completed') return 'completed'

  const latest = events.value[events.value.length - 1]
  if (!latest) return 'idle'
  if (latest.type.startsWith('work.plan') || latest.type === 'task_started') return 'planning'
  if (latest.type === 'artifact_created' || latest.type === 'source_opened' || latest.type.includes('present')) return 'presenting'
  return 'executing'
})

const artifacts = computed<Record<string, any>[]>(() => {
  const summaryArtifacts = finalSummary.value?.artifacts
  if (Array.isArray(summaryArtifacts) && summaryArtifacts.length > 0) return summaryArtifacts
  return events.value
    .filter(event => event.type === 'artifact_created')
    .map(event => event.data)
})

const sources = computed<Record<string, any>[]>(() => {
  const summarySources = finalSummary.value?.sources
  if (Array.isArray(summarySources) && summarySources.length > 0) return summarySources
  return events.value
    .filter(event => event.type === 'source_opened')
    .map(event => event.data)
})

const desktopActions = computed<Record<string, any>[]>(() => {
  const summaryActions = finalSummary.value?.desktop_actions
  if (Array.isArray(summaryActions) && summaryActions.length > 0) return summaryActions
  return events.value
    .filter(event => event.type === 'desktop_action' || event.type === 'browser_action')
    .map(event => event.data)
})

const failures = computed<Record<string, any>[]>(() => {
  const summaryFailures = finalSummary.value?.failures
  if (Array.isArray(summaryFailures) && summaryFailures.length > 0) return summaryFailures
  return events.value
    .filter(event => event.type === 'task_failed' || event.type === 'work.step.failed')
    .map(event => event.data)
})

const latestEvent = computed(() => events.value[events.value.length - 1] || null)

const proofCount = computed(() => (
  artifacts.value.length +
  sources.value.length +
  desktopActions.value.length
))

const completedStepCount = computed(() => steps.value.filter(step => stepStatus(step) === 'completed').length)

const progressPercent = computed(() => {
  if (status.value === 'completed') return 100
  if (status.value === 'failed') return Math.max(8, Math.round((completedStepCount.value / Math.max(steps.value.length, 1)) * 100))
  if (!steps.value.length) return running.value ? 12 : 0
  return Math.max(8, Math.round((completedStepCount.value / steps.value.length) * 100))
})

const feedItems = computed<FeedItem[]>(() => {
  const items: FeedItem[] = []

  if (submittedTask.value) {
    items.push({
      id: 'user-request',
      role: 'user',
      title: t('workmode.roles.operator'),
      message: submittedTask.value,
      meta: t('workmode.labels.request'),
      tone: 'default',
    })
  }

  events.value
    .filter(event => event.type !== 'work.stream.empty')
    .forEach((event, index) => {
      items.push({
        id: `${event.created_at}-${event.type}-${index}`,
        role: eventRole(event.type),
        title: eventTitle(event.type),
        message: event.message,
        meta: `${formatTime(event.created_at)} · ${event.type}`,
        tone: eventTone(event.type),
      })
    })

  return items
})

function stepEventId(event: WorkModeEvent): string | null {
  const step = event.data?.step
  if (step && typeof step === 'object' && typeof (step as Record<string, any>).id === 'string') {
    return (step as Record<string, any>).id
  }
  return null
}

function stepStatus(step: WorkStep): StepStatus {
  let current: StepStatus = 'pending'

  for (const event of events.value) {
    if (stepEventId(event) !== step.id) continue
    if (event.type === 'work.step.started') current = 'running'
    if (event.type === 'work.step.completed') current = 'completed'
    if (event.type === 'work.step.failed') {
      const result = event.data?.result
      if (result && typeof result === 'object' && (result as Record<string, any>).status === 'blocked') {
        current = 'blocked'
      } else {
        current = 'failed'
      }
    }
  }

  return current
}

function stepStatusLabel(value: StepStatus): string {
  const labels: Record<StepStatus, string> = {
    pending: t('workmode.stepStatus.pending'),
    running: t('workmode.stepStatus.running'),
    completed: t('workmode.stepStatus.completed'),
    failed: t('workmode.stepStatus.failed'),
    blocked: t('workmode.stepStatus.blocked'),
  }
  return labels[value]
}

function stepStatusTagType(value: StepStatus) {
  if (value === 'completed') return 'success'
  if (value === 'failed' || value === 'blocked') return 'error'
  if (value === 'running') return 'info'
  return 'default'
}

function eventRole(type: string): FeedItem['role'] {
  if (type.includes('failed') || type.includes('stderr')) return 'system'
  if (type === 'artifact_created' || type === 'source_opened' || type.includes('action')) return 'system'
  return 'assistant'
}

function eventTitle(type: string): string {
  if (type.startsWith('work.plan') || type === 'task_started') return t('workmode.panels.plan')
  if (type.startsWith('work.step')) return t('workmode.panels.steps')
  if (type === 'artifact_created') return t('workmode.panels.artifacts')
  if (type === 'source_opened') return t('workmode.panels.sources')
  if (type.includes('failed')) return t('workmode.panels.failures')
  return t('workmode.roles.assistant')
}

function eventTone(type: string): string {
  if (type.includes('failed') || type === 'task_failed' || type.includes('stderr')) return 'failed'
  if (type.includes('completed') || type === 'task_finished' || type === 'artifact_created') return 'completed'
  if (type.includes('started')) return 'started'
  if (type.includes('confirmation')) return 'warning'
  return 'default'
}

function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

function itemTitle(item: Record<string, any>, fallback: string): string {
  return String(item.title || item.kind || item.action || item.type || fallback)
}

function itemPath(item: Record<string, any>): string {
  return String(item.path || item.url || item.error || item.summary || '')
}

function formatJson(value: Record<string, any>): string {
  return JSON.stringify(value, null, 2)
}

async function copyText(text: string) {
  if (!text) return
  await navigator.clipboard.writeText(text)
  message.success(t('common.copied'))
}

async function scrollFeed() {
  await nextTick()
  const element = feedRef.value
  if (element) element.scrollTop = element.scrollHeight
}

function handleEvent(event: WorkModeEvent) {
  events.value.push(event)
  if (event.type === 'task_finished') {
    finalSummary.value = event.data
  }
  void scrollFeed()
}

function pushLocalEvent(type: string, eventMessage: string) {
  events.value.push({
    type,
    message: eventMessage,
    data: {},
    created_at: new Date().toISOString(),
  })
  void scrollFeed()
}

function streamFinishedWithFailure(): boolean {
  const summary = finalSummary.value as Record<string, any> | null
  return terminalEvent.value?.type === 'task_failed' || summary?.status === 'failed'
}

async function runTask() {
  const input = taskText.value.trim()
  if (!input) {
    message.warning(t('workmode.messages.taskRequired'))
    return
  }

  abortController.value?.abort()
  const controller = new AbortController()
  abortController.value = controller
  running.value = true
  submittedTask.value = input
  events.value = []
  finalSummary.value = null
  errorText.value = ''
  void scrollFeed()

  try {
    await runWorkModeStream(
      { message: input, mode: mode.value },
      {
        signal: controller.signal,
        onEvent: handleEvent,
      },
    )

    if (streamFinishedWithFailure()) {
      message.error(t('workmode.messages.finishedWithFailure'))
    } else {
      message.success(t('workmode.messages.finished'))
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      pushLocalEvent('work.stream.cancelled', t('workmode.messages.cancelled'))
      message.info(t('workmode.messages.cancelled'))
    } else {
      errorText.value = err?.message || t('workmode.messages.failed')
      pushLocalEvent('task_failed', errorText.value)
      message.error(errorText.value)
    }
  } finally {
    if (abortController.value === controller) abortController.value = null
    running.value = false
  }
}

function stopTask() {
  abortController.value?.abort()
}

function useExample(example: string) {
  if (running.value) return
  taskText.value = example
}
</script>

<template>
  <div class="workmode-view" :class="`stage-${currentStage}`">
    <header class="workmode-topbar">
      <div class="topbar-title">
        <span class="topbar-eyebrow">{{ t('workmode.labels.project') }}</span>
        <h2>{{ t('workmode.title') }}</h2>
      </div>
      <div class="topbar-actions">
        <div class="mode-switch" role="group" :aria-label="t('workmode.status.mode')">
          <button
            v-for="option in modeOptions"
            :key="option.value"
            type="button"
            class="mode-chip"
            :class="{ active: mode === option.value }"
            :disabled="running"
            @click="mode = option.value"
          >
            {{ option.label }}
          </button>
        </div>
        <NButton type="primary" size="small" :loading="running" @click="runTask">
          <template #icon>
            <span class="button-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <polygon points="7 4 19 12 7 20 7 4" />
              </svg>
            </span>
          </template>
          {{ t('workmode.actions.run') }}
        </NButton>
        <NButton size="small" quaternary :disabled="!running" @click="stopTask">
          <template #icon>
            <span class="button-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
            </span>
          </template>
          {{ t('workmode.actions.stop') }}
        </NButton>
      </div>
    </header>

    <section class="stage-strip" aria-live="polite">
      <div class="stage-cell stage-current">
        <span class="status-dot" :class="currentStage"></span>
        <div>
          <span class="stage-label">{{ t('workmode.labels.stage') }}</span>
          <strong>{{ stageLabels[currentStage] }}</strong>
        </div>
      </div>
      <div class="stage-cell">
        <span class="stage-label">{{ t('workmode.status.label') }}</span>
        <NTag size="small" :type="statusTagType">{{ statusLabels[status] }}</NTag>
      </div>
      <div class="stage-cell">
        <span class="stage-label">{{ t('workmode.status.route') }}</span>
        <strong>{{ routeLabel }}</strong>
      </div>
      <div class="stage-cell">
        <span class="stage-label">{{ t('workmode.labels.proof') }}</span>
        <strong>{{ proofCount }}</strong>
      </div>
      <div class="stage-cell latest">
        <span class="stage-label">{{ t('workmode.labels.latest') }}</span>
        <strong>{{ latestEvent?.message || t('workmode.states.noEvents') }}</strong>
      </div>
    </section>

    <main class="workmode-console">
      <section class="operator-pane">
        <div ref="feedRef" class="feed-scroll">
          <div v-if="!feedItems.length" class="welcome-panel">
            <h1>{{ t('workmode.title') }}</h1>
            <p>{{ t('workmode.states.noTask') }}</p>
          </div>

          <article
            v-for="item in feedItems"
            :key="item.id"
            class="feed-message"
            :class="[item.role, `tone-${item.tone}`]"
          >
            <div class="feed-role">{{ item.title }}</div>
            <div class="feed-bubble">{{ item.message }}</div>
            <div class="feed-meta">{{ item.meta }}</div>
          </article>
        </div>

        <div class="composer">
          <NInput
            v-model:value="taskText"
            class="task-input"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :placeholder="t('workmode.form.placeholder')"
            :disabled="running"
            @keydown.enter.exact.prevent="runTask"
          />
          <div class="composer-toolbar">
            <div class="example-row">
              <button
                v-for="example in exampleTasks"
                :key="example"
                type="button"
                class="example-chip"
                :disabled="running"
                @click="useExample(example)"
              >
                {{ example }}
              </button>
            </div>
            <div class="composer-context">
              <span>{{ t('workmode.status.mode') }}: {{ modeOptions.find(item => item.value === mode)?.label }}</span>
              <span>{{ t('workmode.labels.stage') }}: {{ stageLabels[currentStage] }}</span>
            </div>
          </div>
        </div>
      </section>

      <aside class="evidence-pane">
        <section class="evidence-card progress-card">
          <div class="card-head">
            <h3>{{ t('workmode.labels.progress') }}</h3>
            <span>{{ completedStepCount }}/{{ steps.length || 0 }}</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${progressPercent}%` }"></div>
          </div>
          <p>{{ stageLabels[currentStage] }}</p>
        </section>

        <section class="evidence-card plan-card">
          <div class="card-head">
            <h3>{{ t('workmode.panels.plan') }}</h3>
            <span>{{ steps.length }} {{ t('workmode.panels.steps') }}</span>
          </div>
          <div v-if="steps.length" class="step-list">
            <div
              v-for="step in steps"
              :key="step.id"
              class="step-row"
              :class="`is-${stepStatus(step)}`"
            >
              <span class="step-dot"></span>
              <div class="step-body">
                <div class="step-title-row">
                  <strong>{{ step.title }}</strong>
                  <NTag size="tiny" :type="stepStatusTagType(stepStatus(step))">
                    {{ stepStatusLabel(stepStatus(step)) }}
                  </NTag>
                </div>
                <p>{{ step.description }}</p>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">{{ t('workmode.states.noPlan') }}</div>
        </section>

        <section class="evidence-card">
          <div class="card-head">
            <h3>{{ t('workmode.panels.artifacts') }}</h3>
            <span>{{ artifacts.length }}</span>
          </div>
          <div v-if="artifacts.length" class="proof-list">
            <div v-for="(artifact, index) in artifacts" :key="`${itemPath(artifact)}-${index}`" class="proof-row">
              <div class="proof-body">
                <strong>{{ itemTitle(artifact, t('workmode.fallbacks.artifact')) }}</strong>
                <span>{{ itemPath(artifact) || formatJson(artifact) }}</span>
              </div>
              <button type="button" class="icon-button" :disabled="!itemPath(artifact)" :title="t('common.copy')" @click="copyText(itemPath(artifact))">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <rect x="9" y="9" width="13" height="13" rx="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </button>
            </div>
          </div>
          <div v-else class="empty-state">{{ t('workmode.states.noArtifacts') }}</div>
        </section>

        <section class="evidence-card">
          <div class="card-head">
            <h3>{{ t('workmode.panels.sources') }}</h3>
            <span>{{ sources.length }}</span>
          </div>
          <div v-if="sources.length" class="proof-list">
            <div v-for="(source, index) in sources" :key="`${itemPath(source)}-${index}`" class="proof-row">
              <div class="proof-body">
                <strong>{{ itemTitle(source, t('workmode.fallbacks.source')) }}</strong>
                <span>{{ itemPath(source) || formatJson(source) }}</span>
              </div>
              <button type="button" class="icon-button" :disabled="!itemPath(source)" :title="t('common.copy')" @click="copyText(itemPath(source))">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <rect x="9" y="9" width="13" height="13" rx="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
              </button>
            </div>
          </div>
          <div v-else class="empty-state">{{ t('workmode.states.noSources') }}</div>
        </section>

        <section class="evidence-card" :class="{ attention: failures.length || errorText }">
          <div class="card-head">
            <h3>{{ t('workmode.panels.failures') }}</h3>
            <span>{{ failures.length }}</span>
          </div>
          <div v-if="failures.length" class="json-list">
            <pre v-for="(failure, index) in failures" :key="index">{{ formatJson(failure) }}</pre>
          </div>
          <div v-else-if="errorText" class="empty-state error-text">{{ errorText }}</div>
          <div v-else class="empty-state">{{ t('workmode.states.noFailures') }}</div>
        </section>

        <section class="evidence-card">
          <div class="card-head">
            <h3>{{ t('workmode.panels.actions') }}</h3>
            <span>{{ desktopActions.length }}</span>
          </div>
          <div v-if="desktopActions.length" class="json-list">
            <pre v-for="(action, index) in desktopActions" :key="index">{{ formatJson(action) }}</pre>
          </div>
          <div v-else class="empty-state">{{ t('workmode.states.noActions') }}</div>
        </section>
      </aside>
    </main>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.workmode-view {
  --wm-surface: #{$bg-card};
  --wm-soft: #{$bg-secondary};
  --wm-border: #{$border-color};
  --wm-text: #{$text-primary};
  --wm-muted: #{$text-muted};
  --wm-secondary: #{$text-secondary};
  --wm-blue: var(--accent-info);
  height: 100%;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, var(--wm-surface), #{$bg-primary} 42%);
  color: var(--wm-text);
}

.workmode-topbar {
  min-height: 68px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--wm-border);
  background: rgba(var(--text-primary-rgb), 0.02);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  flex-shrink: 0;
}

.topbar-title {
  min-width: 0;

  h2 {
    margin-top: 2px;
    font-size: 18px;
    line-height: 1.2;
    font-weight: 700;
  }
}

.topbar-eyebrow,
.stage-label {
  color: var(--wm-muted);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.topbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.mode-switch {
  min-width: 0;
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--wm-border);
  border-radius: $radius-sm;
  background: var(--wm-soft);
}

.mode-chip {
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: $radius-sm;
  background: transparent;
  color: var(--wm-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;

  &.active {
    background: var(--wm-surface);
    color: var(--wm-text);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
  }

  &:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
}

.button-icon {
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;

  svg {
    width: 14px;
    height: 14px;
    fill: currentColor;
    stroke: currentColor;
    stroke-width: 0;
  }
}

.stage-strip {
  min-height: 58px;
  display: grid;
  grid-template-columns: minmax(190px, 1.1fr) minmax(100px, 0.65fr) minmax(120px, 0.75fr) minmax(92px, 0.5fr) minmax(220px, 1.6fr);
  border-bottom: 1px solid var(--wm-border);
  background: var(--wm-surface);
  flex-shrink: 0;
}

.stage-cell {
  min-width: 0;
  padding: 10px 14px;
  border-right: 1px solid $border-light;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;

  &:last-child {
    border-right: 0;
  }

  strong {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
  }
}

.stage-current {
  flex-direction: row;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--wm-muted);
  flex-shrink: 0;
}

.status-dot.planning,
.status-dot.executing,
.status-dot.presenting {
  background: var(--warning);
  box-shadow: 0 0 0 3px rgba(var(--warning-rgb), 0.18);
}

.status-dot.completed {
  background: var(--success);
}

.status-dot.failed,
.status-dot.cancelled {
  background: var(--error);
}

.workmode-console {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(420px, 1fr) minmax(340px, 430px);
  gap: 14px;
  padding: 14px;
  overflow: hidden;
}

.operator-pane,
.evidence-pane {
  min-height: 0;
  min-width: 0;
}

.operator-pane {
  border: 1px solid var(--wm-border);
  border-radius: $radius-sm;
  background: var(--wm-surface);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.feed-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 20px;
}

.welcome-panel {
  max-width: 620px;
  margin: 9vh auto 0;
  text-align: center;

  h1 {
    font-size: 26px;
    line-height: 1.2;
    margin-bottom: 8px;
  }

  p {
    color: var(--wm-secondary);
    font-size: 14px;
  }
}

.feed-message {
  max-width: 760px;
  margin: 0 auto 16px;
  display: flex;
  flex-direction: column;
  gap: 5px;

  &.user {
    align-items: flex-end;
  }
}

.feed-role,
.feed-meta {
  color: var(--wm-muted);
  font-size: 12px;
}

.feed-bubble {
  max-width: min(680px, 100%);
  padding: 12px 14px;
  border-radius: 8px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--wm-text);
  background: var(--wm-surface);
  border: 1px solid var(--wm-border);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}

.feed-message.user .feed-bubble {
  background: var(--wm-soft);
  border-color: transparent;
}

.feed-message.system .feed-bubble {
  background: rgba(var(--text-primary-rgb), 0.025);
}

.feed-message.tone-failed .feed-bubble {
  border-color: rgba(var(--error-rgb), 0.45);
}

.feed-message.tone-completed .feed-bubble {
  border-color: rgba(var(--success-rgb), 0.32);
}

.feed-message.tone-started .feed-bubble {
  border-color: rgba(var(--accent-info-rgb), 0.32);
}

.feed-message.tone-warning .feed-bubble {
  border-color: rgba(var(--warning-rgb), 0.38);
}

.composer {
  flex-shrink: 0;
  margin: 0 14px 14px;
  border: 1px solid var(--wm-border);
  border-radius: 8px;
  background: var(--wm-surface);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.task-input {
  :deep(.n-input),
  :deep(.n-input-wrapper),
  :deep(textarea) {
    background: transparent;
  }
}

.composer-toolbar {
  padding: 8px 10px 10px;
  border-top: 1px solid var(--wm-border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.example-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.example-chip {
  min-height: 26px;
  max-width: 100%;
  padding: 4px 9px;
  border: 1px solid var(--wm-border);
  border-radius: $radius-sm;
  background: var(--wm-soft);
  color: var(--wm-secondary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  text-align: left;

  &:hover:not(:disabled) {
    color: var(--wm-text);
    border-color: var(--wm-muted);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.composer-context {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  color: var(--wm-muted);
  font-size: 12px;
}

.evidence-pane {
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 2px;
}

.evidence-card {
  border: 1px solid var(--wm-border);
  border-radius: $radius-sm;
  background: var(--wm-surface);
  // overflow: hidden;

  &.attention {
    border-color: rgba(var(--error-rgb), 0.45);
  }
}

.card-head {
  min-height: 42px;
  padding: 0 12px;
  border-bottom: 1px solid $border-light;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;

  h3 {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
    font-weight: 700;
  }

  span {
    color: var(--wm-muted);
    font-size: 12px;
    white-space: nowrap;
  }
}

.progress-card {
  padding-bottom: 12px;

  p {
    margin: 8px 12px 0;
    color: var(--wm-secondary);
    font-size: 12px;
  }
}

.progress-track {
  height: 7px;
  margin: 12px 12px 0;
  border-radius: 999px;
  background: var(--wm-soft);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  width: 0;
  border-radius: inherit;
  background: var(--success);
  transition: width 0.25s ease;
}

.step-list {
  padding: 8px 0;
}

.step-row {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 8px;
  padding: 9px 12px;
}

.step-dot {
  width: 9px;
  height: 9px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--wm-muted);
}

.step-row.is-running .step-dot {
  background: var(--warning);
  box-shadow: 0 0 0 3px rgba(var(--warning-rgb), 0.16);
}

.step-row.is-completed .step-dot {
  background: var(--success);
}

.step-row.is-failed .step-dot,
.step-row.is-blocked .step-dot {
  background: var(--error);
}

.step-body {
  min-width: 0;

  p {
    margin-top: 4px;
    color: var(--wm-secondary);
    font-size: 12px;
    line-height: 1.45;
  }
}

.step-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;

  strong {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
  }
}

.proof-list {
  display: flex;
  flex-direction: column;
  padding: 6px 0;
}

.proof-row {
  min-height: 50px;
  padding: 8px 10px 8px 12px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 30px;
  gap: 8px;
  align-items: center;
}

.proof-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    color: var(--wm-text);
    font-size: 13px;
  }

  span {
    color: var(--wm-muted);
    font-family: $font-code;
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.icon-button {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: $radius-sm;
  background: transparent;
  color: var(--wm-secondary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;

  svg {
    width: 15px;
    height: 15px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  &:hover:not(:disabled) {
    background: var(--wm-soft);
    color: var(--wm-text);
  }

  &:disabled {
    opacity: 0.35;
    cursor: default;
  }
}

.json-list {
  padding: 10px;

  pre {
    margin-bottom: 8px;
    padding: 9px;
    border: 1px solid $border-light;
    border-radius: $radius-sm;
    background: $code-bg;
    color: var(--wm-secondary);
    font-family: $font-code;
    font-size: 11px;
    line-height: 1.45;
    white-space: pre-wrap;
    overflow-wrap: anywhere;

    &:last-child {
      margin-bottom: 0;
    }
  }
}

.empty-state {
  min-height: 76px;
  padding: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--wm-muted);
  text-align: center;
  font-size: 12px;
}

.error-text {
  color: var(--error);
}

@media (max-width: 1180px) {
  .stage-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stage-cell {
    border-bottom: 1px solid $border-light;
  }

  .stage-cell.latest {
    grid-column: 1 / -1;
  }

  .workmode-console {
    grid-template-columns: 1fr;
    overflow: auto;
  }

  .operator-pane {
    min-height: 620px;
  }

  .evidence-pane {
    overflow: visible;
  }
}

@media (max-width: $breakpoint-mobile) {
  .workmode-topbar {
    grid-template-columns: 1fr;
    padding: 12px 12px 12px 52px;
  }

  .topbar-actions {
    justify-content: flex-start;
  }

  .mode-switch {
    width: 100%;
  }

  .mode-chip {
    flex: 1;
  }

  .stage-strip {
    grid-template-columns: 1fr;
  }

  .stage-cell {
    border-right: 0;
  }

  .workmode-console {
    padding: 10px;
  }

  .operator-pane {
    min-height: 560px;
  }

  .feed-scroll {
    padding: 14px;
  }

  .composer {
    margin: 0 10px 10px;
  }
}
</style>
