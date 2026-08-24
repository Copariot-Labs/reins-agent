<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton,
  NInput,
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import {
  createOfficeDocument,
  fetchOfficeDocuments,
  fetchOfficeSkills,
  fetchOfficeStatus,
  getOfficePreviewUrl,
  reviseOfficeDocument,
  type OfficeDocument,
  type OfficeFormat,
  type OfficePresentationAudience,
  type OfficePresentationDetail,
  type OfficePresentationStyle,
  type OfficeSkill,
  type OfficeStatus,
} from '@/api/reins/office'
import { downloadFile } from '@/api/reins/download'

const OFFICE_FORMATS: OfficeFormat[] = ['docx', 'xlsx', 'pptx']
const PRESENTATION_STYLES: OfficePresentationStyle[] = ['auto', 'executive', 'modern', 'bold', 'minimal']
const PRESENTATION_AUDIENCES: OfficePresentationAudience[] = ['general', 'executive', 'client', 'team']
const PRESENTATION_DETAILS: OfficePresentationDetail[] = ['concise', 'balanced', 'detailed']

const message = useMessage()
const { locale } = useI18n()
const route = useRoute()
const router = useRouter()

const format = ref<OfficeFormat>('docx')
const skills = ref<OfficeSkill[]>([])
const selectedSkillId = ref('')
const title = ref('')
const prompt = ref('')
const language = ref('zh')
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
const creatingNew = ref(true)

const isChinese = computed(() => locale.value.toLowerCase().startsWith('zh'))
const copy = computed(() => isChinese.value
  ? {
      title: 'Office',
      word: 'Word 文档',
      excel: 'Excel 表格',
      ppt: 'PPT 演示',
      fixedWorkflows: '文档技能',
      recentFiles: '最近文件',
      noFiles: '暂无此类型文件',
      workflowInput: '文件内容要求',
      documentTitle: '文件标题',
      titlePlaceholder: '可选，Reins 也可以根据内容生成',
      language: '文件语言',
      generate: '生成文件',
      generating: '正在生成',
      newFile: '新建文件',
      refresh: '刷新',
      connected: '已连接',
      unavailable: 'Office 服务未完全连接',
      setup: '配置',
      preview: '文件预览',
      rendering: '正在生成预览',
      download: '下载',
      revision: '修改文件',
      revisePlaceholder: '描述需要修改的内容、结构、设计或数据',
      apply: '应用修改',
      revising: '正在修改',
      lastChange: '上次修改',
      revisionCount: '次修改',
      created: '文件已创建',
      revised: '修改已应用',
      promptRequired: '请输入文件内容要求',
      skillRequired: '请选择一个文档技能',
      createFailed: '创建 Office 文件失败',
      reviseFailed: '修改 Office 文件失败',
      loadFailed: '加载 Office 工作流失败',
      downloadFailed: '下载失败',
      downloadSuccess: '下载已开始',
      presentationStyle: '视觉风格',
      presentationAudience: '受众',
      presentationDetail: '内容密度',
      slideCount: '页数',
      selectedWorkflow: '已选技能',
    }
  : {
      title: 'Office',
      word: 'Word documents',
      excel: 'Excel workbooks',
      ppt: 'PPT presentations',
      fixedWorkflows: 'Document skills',
      recentFiles: 'Recent files',
      noFiles: 'No files of this type yet',
      workflowInput: 'Document requirements',
      documentTitle: 'File title',
      titlePlaceholder: 'Optional; Reins can derive it from the content',
      language: 'File language',
      generate: 'Generate file',
      generating: 'Generating',
      newFile: 'New file',
      refresh: 'Refresh',
      connected: 'Connected',
      unavailable: 'Office services need attention',
      setup: 'Setup',
      preview: 'File preview',
      rendering: 'Rendering preview',
      download: 'Download',
      revision: 'Revise file',
      revisePlaceholder: 'Describe the content, structure, design, or data changes',
      apply: 'Apply changes',
      revising: 'Revising',
      lastChange: 'Last change',
      revisionCount: 'modifications',
      created: 'Office file created',
      revised: 'Changes applied',
      promptRequired: 'Enter the document requirements',
      skillRequired: 'Select a document skill',
      createFailed: 'Failed to create Office file',
      reviseFailed: 'Failed to revise Office file',
      loadFailed: 'Failed to load Office workflows',
      downloadFailed: 'Download failed',
      downloadSuccess: 'Download started',
      presentationStyle: 'Visual style',
      presentationAudience: 'Audience',
      presentationDetail: 'Content density',
      slideCount: 'Slides',
      selectedWorkflow: 'Selected skill',
    })

const formatOptions = computed(() => [
  { value: 'docx' as const, label: copy.value.word, mark: 'W' },
  { value: 'xlsx' as const, label: copy.value.excel, mark: 'X' },
  { value: 'pptx' as const, label: copy.value.ppt, mark: 'P' },
])

const languageOptions = [
  { label: '中文', value: 'zh' },
  { label: 'English', value: 'en' },
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

const currentSkills = computed(() => skills.value.filter(skill => skill.format === format.value))
const selectedSkill = computed(() =>
  currentSkills.value.find(skill => skill.id === selectedSkillId.value) || null,
)
const formatDocuments = computed(() => documents.value.filter(document => document.kind === format.value))
const selectedDocument = computed(() =>
  documents.value.find(document => document.id === selectedId.value) || null,
)
const isCreateMode = computed(() => creatingNew.value || !selectedDocument.value)
const servicesReady = computed(() => Boolean(status.value?.available && status.value?.reins_available))
const currentFormat = computed(() => formatOptions.value.find(option => option.value === format.value)!)
const previewUrl = computed(() => {
  const document = selectedDocument.value
  if (!document || isCreateMode.value) return ''
  return getOfficePreviewUrl(document.id, `${document.updated_at}-${previewVersion.value}`)
})
const lastRevision = computed(() => {
  const value = selectedDocument.value?.metadata?.last_revision
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
})

function localizedSkillValue(skill: OfficeSkill | null, field: 'label' | 'description' | 'placeholder'): string {
  if (!skill) return ''
  const suffix = isChinese.value ? 'zh' : 'en'
  return String(skill[`${field}_${suffix}` as keyof OfficeSkill] || '')
}

function queryFormat(value: unknown): OfficeFormat {
  const first = Array.isArray(value) ? value[0] : value
  return OFFICE_FORMATS.includes(String(first) as OfficeFormat)
    ? String(first) as OfficeFormat
    : 'docx'
}

function applySkillDefaults(skill: OfficeSkill | null) {
  if (!skill || skill.format !== 'pptx') return
  const defaults = skill.defaults || {}
  const style = String(defaults.style || '') as OfficePresentationStyle
  const audience = String(defaults.audience || '') as OfficePresentationAudience
  const detail = String(defaults.detail || '') as OfficePresentationDetail
  const count = Number(defaults.slide_count)
  presentationStyle.value = PRESENTATION_STYLES.includes(style) ? style : 'auto'
  presentationAudience.value = PRESENTATION_AUDIENCES.includes(audience) ? audience : 'general'
  presentationDetail.value = PRESENTATION_DETAILS.includes(detail) ? detail : 'balanced'
  slideCount.value = Number.isInteger(count) ? Math.min(Math.max(count, 5), 15) : 8
}

function selectSkill(skill: OfficeSkill) {
  selectedSkillId.value = skill.id
  selectedId.value = null
  creatingNew.value = true
  title.value = ''
  prompt.value = ''
  applySkillDefaults(skill)
}

async function selectFormat(nextFormat: OfficeFormat) {
  if (nextFormat === format.value) return
  await router.push({ name: 'hermes.office', query: { ...route.query, type: nextFormat } })
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
  title.value = ''
  prompt.value = ''
  if (!selectedSkill.value && currentSkills.value.length) {
    selectedSkillId.value = currentSkills.value[0].id
    applySkillDefaults(currentSkills.value[0])
  }
}

function upsertDocument(document: OfficeDocument) {
  documents.value = [document, ...documents.value.filter(item => item.id !== document.id)]
}

function refreshPreview() {
  if (!selectedDocument.value) return
  previewLoading.value = true
  previewVersion.value += 1
}

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

async function loadOffice() {
  loading.value = true
  try {
    const [statusResponse, documentsResponse, skillsResponse] = await Promise.all([
      fetchOfficeStatus(),
      fetchOfficeDocuments(100),
      fetchOfficeSkills(),
    ])
    status.value = statusResponse
    documents.value = documentsResponse.documents.slice().reverse()
    skills.value = skillsResponse.skills
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
  if (isCreateMode.value && !selectedSkill.value) {
    message.error(copy.value.skillRequired)
    return
  }

  working.value = true
  try {
    if (isCreateMode.value && selectedSkill.value) {
      const response = await createOfficeDocument({
        format: format.value,
        skill_id: selectedSkill.value.id,
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
    const saved = await downloadFile(document.path, document.file_name)
    if (saved) message.success(copy.value.downloadSuccess)
  } catch (err: any) {
    message.error(err?.message || copy.value.downloadFailed)
  }
}

watch(() => route.query.type, value => {
  const nextFormat = queryFormat(value)
  if (format.value === nextFormat) return
  format.value = nextFormat
  selectedId.value = null
  creatingNew.value = true
  title.value = ''
  prompt.value = ''
}, { immediate: true })

watch([format, skills], () => {
  if (selectedSkill.value) return
  const first = currentSkills.value[0]
  selectedSkillId.value = first?.id || ''
  applySkillDefaults(first || null)
})

onMounted(loadOffice)
</script>

<template>
  <div class="office-view">
    <header class="page-header">
      <div class="page-title">
        <span class="format-mark large" :class="format">{{ currentFormat.mark }}</span>
        <div>
          <h1>{{ currentFormat.label }}</h1>
          <span v-if="status" class="service-status" :class="{ ready: servicesReady }">
            {{ servicesReady ? copy.connected : copy.unavailable }}
          </span>
        </div>
      </div>

      <div class="format-switch" :aria-label="copy.title">
        <button
          v-for="option in formatOptions"
          :key="option.value"
          type="button"
          :class="{ active: option.value === format }"
          @click="selectFormat(option.value)"
        >
          <span class="format-mark" :class="option.value">{{ option.mark }}</span>
          <span>{{ option.label }}</span>
        </button>
      </div>

      <div class="header-actions">
        <NButton size="small" secondary :loading="loading" @click="loadOffice">
          {{ copy.refresh }}
        </NButton>
        <NButton size="small" type="primary" @click="startNewDocument">
          {{ copy.newFile }}
        </NButton>
      </div>
    </header>

    <section v-if="status && !servicesReady" class="setup-band">
      <strong>{{ copy.setup }}</strong>
      <span>{{ status.error || status.setup_hint }}</span>
    </section>

    <main class="office-workspace">
      <aside class="workflow-rail">
        <div class="rail-heading">
          <strong>{{ copy.fixedWorkflows }}</strong>
          <span>{{ currentSkills.length }}</span>
        </div>

        <div class="skill-list">
          <button
            v-for="skill in currentSkills"
            :key="skill.id"
            type="button"
            class="skill-row"
            :class="{ active: isCreateMode && skill.id === selectedSkillId }"
            @click="selectSkill(skill)"
          >
            <span class="skill-index">{{ String(currentSkills.indexOf(skill) + 1).padStart(2, '0') }}</span>
            <span class="skill-copy">
              <strong>{{ localizedSkillValue(skill, 'label') }}</strong>
              <small>{{ localizedSkillValue(skill, 'description') }}</small>
            </span>
          </button>
          <div v-if="loading && !currentSkills.length" class="rail-loading">
            <NSpin size="small" />
          </div>
        </div>

        <div class="rail-heading recent-heading">
          <strong>{{ copy.recentFiles }}</strong>
          <span>{{ formatDocuments.length }}</span>
        </div>

        <div class="document-list">
          <button
            v-for="document in formatDocuments"
            :key="document.id"
            type="button"
            class="document-row"
            :class="{ active: !isCreateMode && document.id === selectedId }"
            @click="selectDocument(document)"
          >
            <span class="format-mark" :class="document.kind">{{ document.kind.slice(0, 1).toUpperCase() }}</span>
            <span class="document-copy">
              <strong>{{ document.title }}</strong>
              <small>{{ formatDate(document.updated_at || document.created_at) }}</small>
            </span>
            <span v-if="document.revision_count" class="revision-count">{{ document.revision_count }}</span>
          </button>
          <p v-if="!formatDocuments.length && !loading" class="empty-list">{{ copy.noFiles }}</p>
        </div>
      </aside>

      <section v-if="isCreateMode" class="generation-page">
        <header class="workflow-hero">
          <div class="workflow-kicker">
            <span class="format-mark" :class="format">{{ currentFormat.mark }}</span>
            <span>{{ copy.selectedWorkflow }}</span>
          </div>
          <h2>{{ localizedSkillValue(selectedSkill, 'label') }}</h2>
          <p>{{ localizedSkillValue(selectedSkill, 'description') }}</p>
        </header>

        <form class="generation-grid" @submit.prevent="submitInstruction">
          <section class="generation-form">
            <label class="field instruction-field">
              <span>{{ copy.workflowInput }}</span>
              <NInput
                v-model:value="prompt"
                type="textarea"
                :placeholder="localizedSkillValue(selectedSkill, 'placeholder')"
                :autosize="{ minRows: 12, maxRows: 22 }"
                :maxlength="30000"
                show-count
              />
            </label>

            <div class="form-actions">
              <NButton
                type="primary"
                attr-type="submit"
                size="large"
                :loading="working"
                :disabled="!prompt.trim() || !selectedSkill || !servicesReady"
              >
                {{ working ? copy.generating : copy.generate }}
              </NButton>
            </div>
          </section>

          <aside class="options-panel">
            <label class="field">
              <span>{{ copy.documentTitle }}</span>
              <NInput v-model:value="title" :placeholder="copy.titlePlaceholder" :maxlength="180" clearable />
            </label>

            <label class="field">
              <span>{{ copy.language }}</span>
              <NSelect v-model:value="language" :options="languageOptions" />
            </label>

            <template v-if="format === 'pptx'">
              <label class="field">
                <span>{{ copy.presentationStyle }}</span>
                <NSelect v-model:value="presentationStyle" :options="presentationStyleOptions" />
              </label>
              <label class="field">
                <span>{{ copy.slideCount }}</span>
                <NSelect v-model:value="slideCount" :options="slideCountOptions" />
              </label>
              <label class="field">
                <span>{{ copy.presentationAudience }}</span>
                <NSelect v-model:value="presentationAudience" :options="presentationAudienceOptions" />
              </label>
              <label class="field">
                <span>{{ copy.presentationDetail }}</span>
                <NSelect v-model:value="presentationDetail" :options="presentationDetailOptions" />
              </label>
            </template>
          </aside>
        </form>
      </section>

      <section v-else class="document-page">
        <div class="preview-region">
          <div class="preview-toolbar">
            <div class="preview-title">
              <strong>{{ selectedDocument?.title || copy.preview }}</strong>
              <NTag v-if="selectedDocument" size="small" :bordered="false">
                {{ selectedDocument.kind.toUpperCase() }}
              </NTag>
            </div>
            <div class="preview-actions">
              <NButton size="small" quaternary @click="refreshPreview">{{ copy.refresh }}</NButton>
              <NButton size="small" quaternary @click="downloadDocument(selectedDocument)">
                {{ copy.download }}
              </NButton>
            </div>
          </div>
          <div class="preview-canvas">
            <div v-if="previewLoading" class="preview-loading">
              <NSpin size="medium" />
              <span>{{ copy.rendering }}</span>
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
        </div>

        <aside class="revision-panel">
          <div class="revision-heading">
            <div>
              <strong>{{ copy.revision }}</strong>
              <span v-if="selectedDocument">{{ selectedDocument.revision_count }} {{ copy.revisionCount }}</span>
            </div>
          </div>
          <form class="revision-form" @submit.prevent="submitInstruction">
            <label class="field instruction-field">
              <span>{{ copy.workflowInput }}</span>
              <NInput
                v-model:value="prompt"
                type="textarea"
                :placeholder="copy.revisePlaceholder"
                :autosize="{ minRows: 12, maxRows: 22 }"
                :maxlength="30000"
                show-count
              />
            </label>
            <section v-if="lastRevision" class="last-change">
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
              {{ working ? copy.revising : copy.apply }}
            </NButton>
          </form>
        </aside>
      </section>
    </main>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.office-view {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  color: $text-primary;
  background: $bg-primary;
}

.page-header {
  min-height: 68px;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  gap: 18px;
  padding: 10px 22px;
  border-bottom: 1px solid $border-color;
  background: $bg-card;
}

.page-title,
.header-actions,
.workflow-kicker,
.preview-title,
.preview-actions {
  display: flex;
  align-items: center;
}

.page-title {
  gap: 10px;
  min-width: 0;
}

.page-title h1 {
  margin: 0;
  overflow: hidden;
  font-size: 16px;
  line-height: 1.3;
  letter-spacing: 0;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.service-status {
  display: block;
  margin-top: 1px;
  color: #b45309;
  font-size: 10px;
}

.service-status.ready { color: #047857; }

.format-switch {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid $border-color;
  border-radius: 8px;
  background: $bg-secondary;
}

.format-switch button {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border: 0;
  border-radius: 6px;
  color: $text-secondary;
  background: transparent;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.format-switch button:hover { color: $text-primary; }
.format-switch button.active {
  color: $text-primary;
  background: $bg-card;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
  font-weight: 600;
}

.header-actions {
  justify-content: flex-end;
  gap: 8px;
}

.format-mark {
  width: 24px;
  height: 26px;
  display: grid;
  flex: 0 0 24px;
  place-items: center;
  border-radius: 4px;
  color: #fff;
  background: #2563eb;
  font-size: 10px;
  font-weight: 750;
}

.format-mark.xlsx { background: #15803d; }
.format-mark.pptx { background: #c2410c; }
.format-mark.large {
  width: 32px;
  height: 36px;
  flex-basis: 32px;
  font-size: 13px;
}

.setup-band {
  min-height: 40px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 22px;
  border-bottom: 1px solid rgba(245, 158, 11, .38);
  background: rgba(254, 243, 199, .42);
  font-size: 12px;
}

.setup-band span {
  overflow: hidden;
  color: $text-secondary;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.office-workspace {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr);
}

.workflow-rail {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid $border-color;
  background: $bg-card;
}

.rail-heading,
.preview-toolbar,
.revision-heading {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 14px;
  border-bottom: 1px solid $border-color;
}

.rail-heading strong,
.preview-toolbar strong,
.revision-heading strong {
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail-heading span,
.revision-heading span {
  color: $text-muted;
  font-size: 10px;
}

.skill-list {
  flex: 0 0 auto;
  padding: 6px;
}

.skill-row,
.document-row {
  width: 100%;
  border: 1px solid transparent;
  color: inherit;
  background: transparent;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.skill-row {
  min-height: 62px;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 6px;
}

.skill-row:hover,
.document-row:hover { background: $bg-secondary; }

.skill-row.active {
  border-color: rgba(var(--accent-primary-rgb), .22);
  background: rgba(var(--accent-primary-rgb), .075);
}

.skill-index {
  color: $text-muted;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.skill-copy,
.document-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.skill-copy { gap: 3px; }
.skill-copy strong,
.skill-copy small,
.document-copy strong,
.document-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-copy strong {
  font-size: 12px;
  font-weight: 620;
  white-space: nowrap;
}

.skill-copy small {
  display: -webkit-box;
  color: $text-muted;
  font-size: 10px;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.rail-loading {
  min-height: 80px;
  display: grid;
  place-items: center;
}

.recent-heading {
  margin-top: 6px;
  border-top: 1px solid $border-color;
}

.document-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 6px;
}

.document-row {
  min-height: 54px;
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 6px;
}

.document-row.active {
  border-color: rgba(var(--accent-primary-rgb), .22);
  background: rgba(var(--accent-primary-rgb), .075);
}

.document-copy strong,
.document-copy small { white-space: nowrap; }
.document-copy strong { font-size: 11px; font-weight: 600; }
.document-copy small,
.revision-count { color: $text-muted; font-size: 9px; }

.empty-list {
  margin: 18px 8px;
  color: $text-muted;
  font-size: 11px;
}

.generation-page {
  min-width: 0;
  min-height: 0;
  overflow: auto;
}

.workflow-hero {
  max-width: 1080px;
  margin: 0 auto;
  padding: 38px 34px 28px;
  border-bottom: 1px solid $border-color;
}

.workflow-kicker {
  gap: 8px;
  color: $text-muted;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}

.workflow-hero h2 {
  margin: 14px 0 7px;
  font-size: 26px;
  line-height: 1.25;
  letter-spacing: 0;
}

.workflow-hero p {
  max-width: 720px;
  margin: 0;
  color: $text-secondary;
  font-size: 13px;
  line-height: 1.65;
}

.generation-grid {
  max-width: 1080px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 286px;
  gap: 18px;
  margin: 0 auto;
  padding: 28px 34px 44px;
}

.generation-form,
.options-panel {
  min-width: 0;
  border: 1px solid $border-color;
  border-radius: 8px;
  background: $bg-card;
}

.generation-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
}

.options-panel {
  align-self: start;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
}

.field {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.field > span,
.last-change > span {
  color: $text-secondary;
  font-size: 11px;
  font-weight: 620;
}

.instruction-field { flex: 1; }
.form-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 4px;
}

.document-page {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
}

.preview-region,
.revision-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.preview-region { background: $bg-secondary; }
.preview-toolbar {
  flex: 0 0 48px;
  background: $bg-card;
}

.preview-title,
.preview-actions { gap: 8px; min-width: 0; }
.preview-actions { margin-left: auto; }

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

.preview-loading {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  color: #6b7280;
  background: #f3f4f6;
  font-size: 12px;
}

.revision-panel {
  border-left: 1px solid $border-color;
  background: $bg-card;
}

.revision-heading > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.revision-form {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: auto;
  padding: 18px;
}

.last-change {
  padding: 12px 0;
  border-top: 1px solid $border-color;
  border-bottom: 1px solid $border-color;
}

.last-change p {
  margin: 5px 0 0;
  color: $text-secondary;
  font-size: 11px;
  line-height: 1.5;
}

@media (max-width: 1100px) {
  .page-header { grid-template-columns: minmax(160px, 1fr) auto; }
  .format-switch { grid-column: 1 / 3; grid-row: 2; justify-self: center; }
  .office-workspace { grid-template-columns: 236px minmax(0, 1fr); }
  .generation-grid { grid-template-columns: minmax(0, 1fr); }
  .options-panel { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .document-page { grid-template-columns: minmax(0, 1fr) 310px; }
}

@media (max-width: 820px) {
  .office-workspace {
    display: flex;
    flex-direction: column;
    overflow: auto;
  }

  .workflow-rail {
    flex: 0 0 auto;
    max-height: 360px;
    border-right: 0;
    border-bottom: 1px solid $border-color;
  }

  .skill-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .document-list { max-height: 150px; }
  .generation-page { overflow: visible; }
  .document-page { min-height: 720px; grid-template-columns: minmax(0, 1fr); }
  .revision-panel { border-top: 1px solid $border-color; border-left: 0; }
  .preview-region { min-height: 460px; }
}

@media (max-width: $breakpoint-mobile) {
  .page-header {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    padding: 8px 10px 8px 52px;
  }

  .page-title .format-mark { display: none; }
  .service-status { display: none; }
  .header-actions > :first-child { display: none; }
  .format-switch {
    width: 100%;
    grid-column: 1 / 3;
    overflow-x: auto;
    justify-content: stretch;
  }

  .format-switch button {
    flex: 1 0 auto;
    justify-content: center;
    padding-inline: 7px;
  }

  .skill-list { grid-template-columns: minmax(0, 1fr); }
  .workflow-hero { padding: 26px 18px 22px; }
  .workflow-hero h2 { font-size: 22px; }
  .generation-grid { padding: 20px 14px 32px; }
  .options-panel { display: flex; }
}
</style>
