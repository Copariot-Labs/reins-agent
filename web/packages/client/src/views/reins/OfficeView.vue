<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NInput,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  createOfficeDocument,
  fetchOfficeDocuments,
  fetchOfficeStatus,
  getOfficePreviewUrl,
  reviseOfficeDocument,
  type OfficeDocument,
  type OfficeFormat,
  type OfficePresentationAudience,
  type OfficePresentationDetail,
  type OfficePresentationStyle,
  type OfficeStatus,
} from '@/api/reins/office'
import { downloadFile } from '@/api/reins/download'

type FormatFilter = 'all' | OfficeFormat

const message = useMessage()
const { locale } = useI18n()

const format = ref<OfficeFormat>('docx')
const formatFilter = ref<FormatFilter>('all')
const title = ref('')
const prompt = ref('')
const language = ref('en')
const presentationStyle = ref<OfficePresentationStyle>('auto')
const presentationAudience = ref<OfficePresentationAudience>('general')
const presentationDetail = ref<OfficePresentationDetail>('balanced')
const slideCount = ref(8)
const working = ref(false)
const loading = ref(false)
const previewLoading = ref(false)
const previewVersion = ref(0)
const status = ref<OfficeStatus | null>(null)
const documents = ref<OfficeDocument[]>([])
const selectedId = ref<string | null>(null)
const creatingNew = ref(false)

const copy = computed(() => {
  const zh = locale.value.toLowerCase().startsWith('zh')
  if (zh) {
    return {
      title: 'Office',
      newDocument: '新建文件',
      all: '全部',
      files: '文件',
      empty: '暂无 Office 文件',
      untitled: '未命名文件',
      preview: '预览',
      noSelection: '选择一个文件，或新建 Office 文件',
      loadingPreview: '正在生成预览',
      refresh: '刷新',
      download: '下载',
      createHeading: '使用 Reins 创建',
      reviseHeading: '使用 Reins 修改',
      prompt: '指令',
      createPlaceholder: '例如：创建一份包含进度、负责人和截止日期的物业维修跟踪表',
      presentationPlaceholder: '例如：为客户创建一份现代产品发布方案，包含市场机会、计划、时间线和下一步',
      documentPlaceholder: '例如：创建一份完整的项目提案，包含背景、建议、预算和后续步骤',
      revisePlaceholder: '例如：增加风险汇总，并把已逾期项目标为高优先级',
      documentTitle: '标题',
      titlePlaceholder: '可选',
      language: '语言',
      presentationStyle: '视觉风格',
      presentationAudience: '受众',
      presentationDetail: '内容密度',
      slideCount: '页数',
      create: '创建文件',
      apply: '应用修改',
      creating: 'Reins 正在创建',
      revising: 'Reins 正在修改',
      created: '文件已创建',
      revised: '修改已应用',
      revision: '次修改',
      validated: '已验证',
      promptRequired: '请输入 Office 指令',
      createFailed: '创建 Office 文件失败',
      reviseFailed: '修改 Office 文件失败',
      loadFailed: '加载 Office 文件失败',
      downloadFailed: '下载失败',
      downloadSuccess: '下载已开始',
      ready: 'Reins 与 OfficeCLI 已连接',
      partial: 'Office 服务未完全连接',
      setup: '配置',
      lastChange: '上次修改',
    }
  }
  return {
    title: 'Office',
    newDocument: 'New document',
    all: 'All',
    files: 'Files',
    empty: 'No Office files yet',
    untitled: 'Untitled document',
    preview: 'Preview',
    noSelection: 'Select a file or create a new Office document',
    loadingPreview: 'Rendering preview',
    refresh: 'Refresh',
    download: 'Download',
    createHeading: 'Create with Reins',
    reviseHeading: 'Revise with Reins',
    prompt: 'Instruction',
    createPlaceholder: 'Example: create a property maintenance tracker with progress, owners, and due dates',
    presentationPlaceholder: 'Example: create a modern client deck for a product launch with the opportunity, plan, timeline, and next steps',
    documentPlaceholder: 'Example: create a complete project proposal with context, recommendations, budget, and next steps',
    revisePlaceholder: 'Example: add a risk summary and mark overdue items as high priority',
    documentTitle: 'Title',
    titlePlaceholder: 'Optional',
    language: 'Language',
    presentationStyle: 'Visual style',
    presentationAudience: 'Audience',
    presentationDetail: 'Content density',
    slideCount: 'Slides',
    create: 'Create file',
    apply: 'Apply revision',
    creating: 'Reins is creating',
    revising: 'Reins is revising',
    created: 'Office file created',
    revised: 'Revision applied',
    revision: 'revisions',
    validated: 'Validated',
    promptRequired: 'Enter an Office instruction',
    createFailed: 'Failed to create Office file',
    reviseFailed: 'Failed to revise Office file',
    loadFailed: 'Failed to load Office files',
    downloadFailed: 'Download failed',
    downloadSuccess: 'Download started',
    ready: 'Reins and OfficeCLI connected',
    partial: 'Office services need attention',
    setup: 'Setup',
    lastChange: 'Last change',
  }
})

const formatOptions = [
  { label: 'Word', value: 'docx' },
  { label: 'Excel', value: 'xlsx' },
  { label: 'PowerPoint', value: 'pptx' },
]

const languageOptions = [
  { label: 'English', value: 'en' },
  { label: '中文', value: 'zh' },
  { label: '日本語', value: 'ja' },
  { label: '한국어', value: 'ko' },
]

const presentationStyleOptions = [
  { label: 'Reins choice', value: 'auto' },
  { label: 'Executive', value: 'executive' },
  { label: 'Modern', value: 'modern' },
  { label: 'Bold', value: 'bold' },
  { label: 'Minimal', value: 'minimal' },
]

const presentationAudienceOptions = [
  { label: 'General', value: 'general' },
  { label: 'Executives', value: 'executive' },
  { label: 'Clients', value: 'client' },
  { label: 'Internal team', value: 'team' },
]

const presentationDetailOptions = [
  { label: 'Concise', value: 'concise' },
  { label: 'Balanced', value: 'balanced' },
  { label: 'Detailed', value: 'detailed' },
]

const slideCountOptions = [6, 8, 10, 12, 15].map(value => ({ label: String(value), value }))

const selectedDocument = computed(() =>
  documents.value.find(document => document.id === selectedId.value) || null,
)

const filteredDocuments = computed(() => {
  if (formatFilter.value === 'all') return documents.value
  return documents.value.filter(document => document.kind === formatFilter.value)
})

const isCreateMode = computed(() => creatingNew.value || !selectedDocument.value)
const createPlaceholder = computed(() => {
  if (format.value === 'pptx') return copy.value.presentationPlaceholder
  if (format.value === 'docx') return copy.value.documentPlaceholder
  return copy.value.createPlaceholder
})
const servicesReady = computed(() => Boolean(status.value?.available && status.value?.reins_available))
const previewUrl = computed(() => {
  const document = selectedDocument.value
  if (!document || isCreateMode.value) return ''
  return getOfficePreviewUrl(document.id, `${document.updated_at}-${previewVersion.value}`)
})

const lastRevision = computed(() => {
  const value = selectedDocument.value?.metadata?.last_revision
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
})

function formatDate(value: string): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function upsertDocument(document: OfficeDocument) {
  documents.value = [document, ...documents.value.filter(item => item.id !== document.id)]
}

function selectDocument(document: OfficeDocument) {
  selectedId.value = document.id
  creatingNew.value = false
  prompt.value = ''
  previewLoading.value = true
}

function startNewDocument() {
  selectedId.value = null
  creatingNew.value = true
  prompt.value = ''
  title.value = ''
}

function refreshPreview() {
  if (!selectedDocument.value) return
  previewLoading.value = true
  previewVersion.value += 1
}

async function loadOffice() {
  loading.value = true
  try {
    const [statusResponse, documentsResponse] = await Promise.all([
      fetchOfficeStatus(),
      fetchOfficeDocuments(100),
    ])
    status.value = statusResponse
    documents.value = documentsResponse.documents.slice().reverse()
    if (selectedId.value) {
      selectedId.value = documents.value.some(item => item.id === selectedId.value)
        ? selectedId.value
        : null
    }
    if (!selectedId.value && !creatingNew.value && documents.value.length) {
      selectDocument(documents.value[0])
    }
  } catch (err: any) {
    message.error(err?.message || copy.value.loadFailed)
  } finally {
    loading.value = false
  }
}

async function submitInstruction() {
  const cleanPrompt = prompt.value.trim()
  if (!cleanPrompt) {
    message.error(copy.value.promptRequired)
    return
  }

  working.value = true
  try {
    if (isCreateMode.value) {
      const response = await createOfficeDocument({
        format: format.value,
        prompt: cleanPrompt,
        title: title.value.trim() || undefined,
        language: language.value,
        ...(format.value === 'pptx'
          ? {
              presentation: {
                style: presentationStyle.value,
                audience: presentationAudience.value,
                detail: presentationDetail.value,
                slide_count: slideCount.value,
              },
            }
          : {}),
      })
      upsertDocument(response.document)
      selectDocument(response.document)
      title.value = ''
      message.success(copy.value.created)
    } else if (selectedDocument.value) {
      const response = await reviseOfficeDocument(selectedDocument.value.id, cleanPrompt)
      upsertDocument(response.document)
      selectedId.value = response.document.id
      prompt.value = ''
      refreshPreview()
      message.success(copy.value.revised)
    }
  } catch (err: any) {
    message.error(err?.message || (isCreateMode.value ? copy.value.createFailed : copy.value.reviseFailed))
  } finally {
    working.value = false
  }
}

async function downloadDocument(document: OfficeDocument | null) {
  if (!document) return
  try {
    await downloadFile(document.path, document.file_name)
    message.success(copy.value.downloadSuccess)
  } catch (err: any) {
    message.error(err?.message || copy.value.downloadFailed)
  }
}

watch(formatFilter, value => {
  if (value === 'all' || !selectedDocument.value || selectedDocument.value.kind === value) return
  const first = documents.value.find(document => document.kind === value)
  if (first) selectDocument(first)
})

onMounted(loadOffice)
</script>

<template>
  <div class="office-view">
    <header class="page-header">
      <div class="title-group">
        <h1>{{ copy.title }}</h1>
        <span
          v-if="status"
          class="service-status"
          :class="{ ready: servicesReady }"
        >
          {{ servicesReady ? copy.ready : copy.partial }}
        </span>
      </div>
      <div class="header-actions">
        <NButton size="small" secondary :loading="loading" @click="loadOffice">
          {{ copy.refresh }}
        </NButton>
        <NButton size="small" type="primary" @click="startNewDocument">
          {{ copy.newDocument }}
        </NButton>
      </div>
    </header>

    <section v-if="status && !servicesReady" class="setup-band">
      <strong>{{ copy.setup }}</strong>
      <span>{{ status.error || status.setup_hint }}</span>
    </section>

    <main class="office-workspace">
      <aside class="document-rail">
        <div class="rail-header">
          <strong>{{ copy.files }}</strong>
          <span>{{ documents.length }}</span>
        </div>
        <NRadioGroup v-model:value="formatFilter" size="small" class="filter-control">
          <NRadioButton value="all">{{ copy.all }}</NRadioButton>
          <NRadioButton value="docx">W</NRadioButton>
          <NRadioButton value="xlsx">X</NRadioButton>
          <NRadioButton value="pptx">P</NRadioButton>
        </NRadioGroup>

        <div class="document-list" :class="{ loading }">
          <button
            v-for="document in filteredDocuments"
            :key="document.id"
            type="button"
            class="document-row"
            :class="{ active: document.id === selectedId && !creatingNew }"
            @click="selectDocument(document)"
          >
            <span class="format-mark" :class="document.kind">{{ document.kind.slice(0, 1).toUpperCase() }}</span>
            <span class="document-copy">
              <strong>{{ document.title || copy.untitled }}</strong>
              <small>{{ formatDate(document.updated_at || document.created_at) }}</small>
            </span>
            <span v-if="document.revision_count" class="revision-count">{{ document.revision_count }}</span>
          </button>
          <p v-if="!filteredDocuments.length && !loading" class="empty-list">{{ copy.empty }}</p>
        </div>
      </aside>

      <section class="preview-region">
        <div class="preview-toolbar">
          <div class="preview-title">
            <strong>{{ selectedDocument?.title || copy.preview }}</strong>
            <NTag v-if="selectedDocument" size="small" :bordered="false">
              {{ selectedDocument.kind.toUpperCase() }}
            </NTag>
            <NTag v-if="lastRevision" size="small" :bordered="false" type="success">
              {{ copy.validated }}
            </NTag>
          </div>
          <div v-if="selectedDocument && !isCreateMode" class="preview-actions">
            <NButton size="small" quaternary @click="refreshPreview">{{ copy.refresh }}</NButton>
            <NButton size="small" quaternary @click="downloadDocument(selectedDocument)">
              {{ copy.download }}
            </NButton>
          </div>
        </div>

        <div class="preview-canvas">
          <div v-if="!previewUrl" class="preview-empty">
            <span>{{ copy.noSelection }}</span>
          </div>
          <div v-else-if="previewLoading" class="preview-loading">
            <NSpin size="medium" />
            <span>{{ copy.loadingPreview }}</span>
          </div>
          <iframe
            v-if="previewUrl"
            :key="previewUrl"
            :src="previewUrl"
            :title="selectedDocument?.file_name || copy.preview"
            class="office-preview-frame"
            sandbox="allow-scripts"
            @load="previewLoading = false"
          />
        </div>
      </section>

      <aside class="reins-panel">
        <div class="composer-heading">
          <div>
            <strong>{{ isCreateMode ? copy.createHeading : copy.reviseHeading }}</strong>
            <span v-if="selectedDocument && !isCreateMode">
              {{ selectedDocument.revision_count }} {{ copy.revision }}
            </span>
          </div>
        </div>

        <form class="composer-form" @submit.prevent="submitInstruction">
          <div v-if="isCreateMode" class="create-options">
            <NRadioGroup v-model:value="format" size="small">
              <NRadioButton
                v-for="option in formatOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </NRadioButton>
            </NRadioGroup>

            <section v-if="format === 'pptx'" class="presentation-options">
              <label class="field">
                <span>{{ copy.presentationStyle }}</span>
                <NSelect
                  v-model:value="presentationStyle"
                  :options="presentationStyleOptions"
                  size="small"
                />
              </label>

              <label class="field">
                <span>{{ copy.slideCount }}</span>
                <NSelect
                  v-model:value="slideCount"
                  :options="slideCountOptions"
                  size="small"
                />
              </label>

              <label class="field">
                <span>{{ copy.presentationAudience }}</span>
                <NSelect
                  v-model:value="presentationAudience"
                  :options="presentationAudienceOptions"
                  size="small"
                />
              </label>

              <label class="field">
                <span>{{ copy.presentationDetail }}</span>
                <NSelect
                  v-model:value="presentationDetail"
                  :options="presentationDetailOptions"
                  size="small"
                />
              </label>
            </section>

            <label class="field">
              <span>{{ copy.documentTitle }}</span>
              <NInput v-model:value="title" :placeholder="copy.titlePlaceholder" :maxlength="180" clearable />
            </label>

            <label class="field">
              <span>{{ copy.language }}</span>
              <NSelect
                v-model:value="language"
                :options="languageOptions"
                size="small"
                :consistent-menu-width="false"
              />
            </label>
          </div>

          <label class="field instruction-field">
            <span>{{ copy.prompt }}</span>
            <NInput
              v-model:value="prompt"
              type="textarea"
              :placeholder="isCreateMode ? createPlaceholder : copy.revisePlaceholder"
              :autosize="{ minRows: 10, maxRows: 18 }"
              :maxlength="30000"
              show-count
            />
          </label>

          <section v-if="lastRevision && !isCreateMode" class="last-change">
            <span>{{ copy.lastChange }}</span>
            <p>{{ lastRevision.summary }}</p>
          </section>

          <NButton
            type="primary"
            attr-type="submit"
            block
            :loading="working"
            :disabled="!prompt.trim() || !servicesReady"
          >
            {{ working
              ? (isCreateMode ? copy.creating : copy.revising)
              : (isCreateMode ? copy.create : copy.apply) }}
          </NButton>
        </form>
      </aside>
    </main>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.office-view {
  min-height: 100%;
  color: $text-primary;
  background: $bg-primary;
}

.page-header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 24px;
  border-bottom: 1px solid $border-color;
  background: $bg-card;
}

.title-group,
.header-actions,
.preview-title,
.preview-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.page-header h1 {
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
  letter-spacing: 0;
}

.service-status {
  color: #b45309;
  font-size: 12px;
  white-space: nowrap;
}

.service-status.ready {
  color: #047857;
}

.setup-band {
  min-height: 42px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 24px;
  border-bottom: 1px solid rgba(245, 158, 11, 0.38);
  background: rgba(254, 243, 199, 0.42);
  font-size: 13px;
}

.setup-band span {
  overflow: hidden;
  color: $text-secondary;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.office-workspace {
  display: grid;
  grid-template-columns: 250px minmax(420px, 1fr) 340px;
  height: calc(100vh - 64px);
  min-height: 620px;
}

.setup-band + .office-workspace {
  height: calc(100vh - 106px);
}

.document-rail,
.preview-region,
.reins-panel {
  min-width: 0;
  min-height: 0;
  background: $bg-card;
}

.document-rail {
  display: flex;
  flex-direction: column;
  border-right: 1px solid $border-color;
}

.rail-header,
.preview-toolbar,
.composer-heading {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 14px;
  border-bottom: 1px solid $border-color;
}

.rail-header strong,
.preview-toolbar strong,
.composer-heading strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail-header span,
.composer-heading span {
  color: $text-muted;
  font-size: 11px;
}

.filter-control {
  padding: 10px 12px;
  border-bottom: 1px solid $border-color;
}

.document-list {
  flex: 1;
  overflow: auto;
  padding: 6px;
}

.document-list.loading {
  opacity: 0.62;
}

.document-row {
  width: 100%;
  min-height: 58px;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.document-row:hover {
  background: $bg-secondary;
}

.document-row.active {
  border-color: rgba(59, 130, 246, 0.28);
  background: rgba(59, 130, 246, 0.08);
}

.format-mark {
  width: 28px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 4px;
  color: #fff;
  background: #2563eb;
  font-size: 12px;
  font-weight: 700;
}

.format-mark.xlsx {
  background: #15803d;
}

.format-mark.pptx {
  background: #c2410c;
}

.document-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.document-copy strong,
.document-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-copy strong {
  font-size: 12px;
  font-weight: 600;
}

.document-copy small,
.revision-count {
  color: $text-muted;
  font-size: 10px;
}

.revision-count {
  min-width: 18px;
  text-align: right;
}

.empty-list {
  margin: 20px 10px;
  color: $text-muted;
  font-size: 12px;
}

.preview-region {
  display: flex;
  flex-direction: column;
  background: $bg-secondary;
}

.preview-toolbar {
  flex: 0 0 52px;
  padding: 0 16px;
  background: $bg-card;
}

.preview-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: #e5e7eb;
}

.office-preview-frame {
  width: 100%;
  height: 100%;
  display: block;
  border: 0;
  background: #fff;
}

.preview-empty,
.preview-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #6b7280;
  background: #f3f4f6;
  font-size: 13px;
  z-index: 1;
}

.preview-loading {
  flex-direction: column;
}

.reins-panel {
  display: flex;
  flex-direction: column;
  border-left: 1px solid $border-color;
}

.composer-heading > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.composer-form {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow: auto;
  padding: 16px;
}

.create-options {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.presentation-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 0;
  border-top: 1px solid $border-color;
  border-bottom: 1px solid $border-color;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 0;
}

.field > span,
.last-change > span {
  color: $text-secondary;
  font-size: 11px;
  font-weight: 600;
}

.instruction-field {
  flex: 1;
}

.last-change {
  padding: 10px 0;
  border-top: 1px solid $border-color;
  border-bottom: 1px solid $border-color;
}

.last-change p {
  margin: 5px 0 0;
  color: $text-secondary;
  font-size: 12px;
  line-height: 1.5;
}

@media (max-width: 1180px) {
  .office-workspace {
    grid-template-columns: 220px minmax(360px, 1fr) 310px;
  }
}

@media (max-width: 940px) {
  .office-workspace,
  .setup-band + .office-workspace {
    grid-template-columns: 210px minmax(0, 1fr);
    grid-template-rows: minmax(440px, 1fr) auto;
    height: auto;
    min-height: calc(100vh - 64px);
  }

  .document-rail {
    grid-row: 1 / 3;
  }

  .reins-panel {
    border-top: 1px solid $border-color;
    border-left: 0;
  }

  .composer-form {
    max-height: 440px;
  }
}

@media (max-width: $breakpoint-mobile) {
  .page-header {
    height: 58px;
    padding: 0 12px 0 54px;
  }

  .service-status,
  .header-actions > :first-child {
    display: none;
  }

  .setup-band {
    padding: 8px 12px;
  }

  .office-workspace,
  .setup-band + .office-workspace {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .document-rail {
    max-height: 220px;
    border-right: 0;
    border-bottom: 1px solid $border-color;
  }

  .document-list {
    min-height: 100px;
  }

  .preview-region {
    min-height: 460px;
  }

  .reins-panel {
    min-height: 420px;
  }
}
</style>
