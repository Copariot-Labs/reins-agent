<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton,
  NInput,
  NSelect,
  NSpin,
  NTag,
  useMessage,
  type InputInst,
} from 'naive-ui'
import {
  cancelOfficeOperation,
  fetchOfficeDocuments,
  fetchOfficeOperation,
  fetchOfficePreviewHtml,
  fetchOfficeSkills,
  fetchOfficeStatus,
  importOfficeDocument,
  startOfficeCreateOperation,
  startOfficeRevisionOperation,
  type OfficeDocument,
  type OfficeFormat,
  type OfficeOperation,
  type OfficeProgressEvent,
  type OfficePresentationAudience,
  type OfficePresentationDetail,
  type OfficePresentationStyle,
  type OfficeSkill,
  type OfficeStatus,
} from '@/api/reins/office'
import { downloadFile } from '@/api/reins/download'
import { OFFICE_FORMAT_NAV_ITEMS, officeFormatFromQuery } from '@/shared/office-formats'

const PRESENTATION_STYLES: OfficePresentationStyle[] = ['auto', 'executive', 'modern', 'bold', 'minimal']
const PRESENTATION_AUDIENCES: OfficePresentationAudience[] = ['general', 'executive', 'client', 'team']
const PRESENTATION_DETAILS: OfficePresentationDetail[] = ['concise', 'balanced', 'detailed']
const LONG_RUNNING_NOTICE_MS = 5 * 60 * 1000

const message = useMessage()
const { locale } = useI18n()
const route = useRoute()
const router = useRouter()

const format = ref<OfficeFormat>('docx')
const skills = ref<OfficeSkill[]>([])
const loading = ref(false)
const previewLoading = ref(false)
const previewVersion = ref(0)
const previewHtml = ref('')
const previewError = ref('')
const promptInputRef = ref<InputInst | null>(null)
const officeFileInputRef = ref<HTMLInputElement | null>(null)
const status = ref<OfficeStatus | null>(null)
const documents = ref<OfficeDocument[]>([])
let previewRunId = 0

interface PendingOfficeFile {
  id: string
  file: File
  importedDocument?: OfficeDocument
}

interface OfficeFormatTaskState {
  selectedSkillId: string
  title: string
  prompt: string
  language: string
  presentationStyle: OfficePresentationStyle
  presentationAudience: OfficePresentationAudience
  presentationDetail: OfficePresentationDetail
  slideCount: number
  selectedId: string | null
  creatingNew: boolean
  longRunning: boolean
  working: boolean
  importing: boolean
  canceling: boolean
  runId: number
  operation: OfficeOperation | null
  transportError: string
  pendingFiles: PendingOfficeFile[]
}

function createFormatTaskState(): OfficeFormatTaskState {
  return {
    selectedSkillId: '',
    title: '',
    prompt: '',
    language: 'zh',
    presentationStyle: 'auto',
    presentationAudience: 'general',
    presentationDetail: 'balanced',
    slideCount: 8,
    selectedId: null,
    creatingNew: true,
    longRunning: false,
    working: false,
    importing: false,
    canceling: false,
    runId: 0,
    operation: null,
    transportError: '',
    pendingFiles: [],
  }
}

const formatTaskStates = reactive<Record<OfficeFormat, OfficeFormatTaskState>>({
  docx: createFormatTaskState(),
  xlsx: createFormatTaskState(),
  pptx: createFormatTaskState(),
})
const currentTaskState = computed(() => formatTaskStates[format.value])
const selectedSkillId = computed({
  get: () => currentTaskState.value.selectedSkillId,
  set: (value: string) => { currentTaskState.value.selectedSkillId = value },
})
const title = computed({
  get: () => currentTaskState.value.title,
  set: (value: string) => { currentTaskState.value.title = value },
})
const prompt = computed({
  get: () => currentTaskState.value.prompt,
  set: (value: string) => { currentTaskState.value.prompt = value },
})
const language = computed({
  get: () => currentTaskState.value.language,
  set: (value: string) => { currentTaskState.value.language = value },
})
const presentationStyle = computed({
  get: () => currentTaskState.value.presentationStyle,
  set: (value: OfficePresentationStyle) => { currentTaskState.value.presentationStyle = value },
})
const presentationAudience = computed({
  get: () => currentTaskState.value.presentationAudience,
  set: (value: OfficePresentationAudience) => { currentTaskState.value.presentationAudience = value },
})
const presentationDetail = computed({
  get: () => currentTaskState.value.presentationDetail,
  set: (value: OfficePresentationDetail) => { currentTaskState.value.presentationDetail = value },
})
const slideCount = computed({
  get: () => currentTaskState.value.slideCount,
  set: (value: number) => { currentTaskState.value.slideCount = value },
})
const selectedId = computed({
  get: () => currentTaskState.value.selectedId,
  set: (value: string | null) => { currentTaskState.value.selectedId = value },
})
const creatingNew = computed({
  get: () => currentTaskState.value.creatingNew,
  set: (value: boolean) => { currentTaskState.value.creatingNew = value },
})
const longRunning = computed(() => currentTaskState.value.longRunning)
const working = computed(() => currentTaskState.value.working)
const importing = computed(() => currentTaskState.value.importing)
const cancelingOperation = computed(() => currentTaskState.value.canceling)
const activeOperation = computed(() => currentTaskState.value.operation)
const operationTransportError = computed(() => currentTaskState.value.transportError)
const pendingFiles = computed(() => currentTaskState.value.pendingFiles)
const longRunningTimers: Partial<Record<OfficeFormat, number>> = {}

const isChinese = computed(() => locale.value.toLowerCase().startsWith('zh'))
const copy = computed(() => isChinese.value
  ? {
      title: 'Office',
      fixedWorkflows: '文档技能',
      recentFiles: '最近文件',
      noFiles: '暂无此类型文件',
      workflowInput: '文件内容要求',
      documentTitle: '文件标题',
      titlePlaceholder: '可选，Reins 也可以根据内容生成',
      language: '文件语言',
      generate: '生成文件',
      generating: '正在生成',
      importFile: '导入文件',
      modifyingFiles: '正在修改',
      pendingFiles: '待修改文件',
      removeFile: '移除文件',
      modifyFiles: '修改',
      filesRevised: '文件已修改并保存',
      importFailed: '导入 Office 文件失败',
      importTypeMismatch: '当前区域仅支持 {extension} 文件',
      importInvalid: '所选文件不是有效的 {extension} Office 文件，或文件已经损坏',
      importTooLarge: '文件不能超过 50 MB',
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
      activity: '处理过程',
      queued: '等待开始',
      running: '处理中',
      needs_input: '需要补充信息',
      completed: '已完成',
      failed: '处理失败',
      cancelled: '已取消',
      cancelTask: '取消任务',
      cancelling: '正在取消',
      cancelFailed: '取消任务失败',
      waitingForProgress: '正在连接 Office 处理任务',
      longRunningNotice: '生成所需时间比平时更长。Reins 仍在处理中，您可以继续等待或取消任务。',
      suggestion: '建议',
      clarificationExample: '例如',
      technicalDetail: '错误详情',
      previewFailed: '预览生成失败',
      retry: '重试',
      resultMissing: '处理已结束，但没有返回文件。',
    }
  : {
      title: 'Office',
      fixedWorkflows: 'Document skills',
      recentFiles: 'Recent files',
      noFiles: 'No files of this type yet',
      workflowInput: 'Document requirements',
      documentTitle: 'File title',
      titlePlaceholder: 'Optional; Reins can derive it from the content',
      language: 'File language',
      generate: 'Generate file',
      generating: 'Generating',
      importFile: 'Import file',
      modifyingFiles: 'Modifying',
      pendingFiles: 'Files to modify',
      removeFile: 'Remove file',
      modifyFiles: 'Modify',
      filesRevised: 'Files modified and saved',
      importFailed: 'Failed to import Office file',
      importTypeMismatch: 'This section only accepts {extension} files',
      importInvalid: 'The selected file is not a valid {extension} Office file or is damaged',
      importTooLarge: 'Files cannot exceed 50 MB',
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
      activity: 'Activity',
      queued: 'Waiting',
      running: 'In progress',
      needs_input: 'More information needed',
      completed: 'Completed',
      failed: 'Failed',
      cancelled: 'Cancelled',
      cancelTask: 'Cancel task',
      cancelling: 'Cancelling',
      cancelFailed: 'Failed to cancel task',
      waitingForProgress: 'Connecting to the Office task',
      longRunningNotice: 'Generation is taking longer than usual. Reins is still working; you can continue waiting or cancel the task.',
      suggestion: 'Suggestion',
      clarificationExample: 'Example',
      technicalDetail: 'Error detail',
      previewFailed: 'Preview failed',
      retry: 'Retry',
      resultMissing: 'The operation finished without returning a document.',
    })

const formatOptions = computed(() => OFFICE_FORMAT_NAV_ITEMS.map(item => ({
  value: item.value,
  label: isChinese.value ? item.labelZh : item.labelEn,
  mark: item.mark,
})))

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
const officeImportAccept = computed(() => ({
  docx: '.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pptx: '.pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation',
})[format.value])
const operationStatusText = computed(() => {
  const operationStatus = activeOperation.value?.status
  if (!operationStatus) return ''
  return copy.value[operationStatus]
})
const canCancelOperation = computed(() =>
  activeOperation.value?.status === 'queued' || activeOperation.value?.status === 'running',
)
const lastRevision = computed(() => {
  const value = selectedDocument.value?.metadata?.last_revision
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
})

function localizedProgress(event: OfficeProgressEvent): string {
  return isChinese.value ? event.message_zh : event.message_en
}

function localizedOperationError(field: 'title' | 'message' | 'suggestion'): string {
  const error = activeOperation.value?.error
  if (!error) return ''
  return isChinese.value
    ? error[`${field}_zh`]
    : error[`${field}_en`]
}

function localizedOperationClarification(field: 'title' | 'message' | 'example'): string {
  const clarification = activeOperation.value?.clarification
  if (!clarification) return ''
  return isChinese.value
    ? clarification[`${field}_zh`]
    : clarification[`${field}_en`]
}

async function focusPromptInput() {
  await nextTick()
  promptInputRef.value?.focus()
}

function localizedSkillValue(skill: OfficeSkill | null, field: 'label' | 'description' | 'placeholder'): string {
  if (!skill) return ''
  const suffix = isChinese.value ? 'zh' : 'en'
  return String(skill[`${field}_${suffix}` as keyof OfficeSkill] || '')
}

function queryFormat(value: unknown): OfficeFormat {
  return officeFormatFromQuery(value)
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

function resetOperationActivity() {
  const taskState = currentTaskState.value
  taskState.runId += 1
  taskState.operation = null
  taskState.transportError = ''
}

function selectSkill(skill: OfficeSkill) {
  if (working.value) return
  resetOperationActivity()
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

function selectDocument(document: OfficeDocument, preserveActivity = false) {
  if (working.value && !preserveActivity) return
  if (!preserveActivity) resetOperationActivity()
  currentTaskState.value.pendingFiles = []
  selectedId.value = document.id
  creatingNew.value = false
  prompt.value = ''
}

function startNewDocument() {
  if (working.value) return
  resetOperationActivity()
  currentTaskState.value.pendingFiles = []
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

function openOfficeImportPicker() {
  if (working.value || importing.value) return
  officeFileInputRef.value?.click()
}

function pendingFileId(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function removePendingFile(id: string) {
  if (working.value) return
  currentTaskState.value.pendingFiles = pendingFiles.value.filter(item => item.id !== id)
}

function handleOfficeImport(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return

  const selectedFormat = format.value
  const expectedExtension = `.${selectedFormat}`
  const existingIds = new Set(pendingFiles.value.map(item => item.id))
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith(expectedExtension)) {
      message.error(copy.value.importTypeMismatch.replace('{extension}', expectedExtension))
      continue
    }
    if (file.size > 50 * 1024 * 1024) {
      message.error(copy.value.importTooLarge)
      continue
    }
    const id = pendingFileId(file)
    if (existingIds.has(id)) continue
    currentTaskState.value.pendingFiles.push({ id, file })
    existingIds.add(id)
  }
}

function refreshPreview() {
  if (!selectedDocument.value) return
  previewVersion.value += 1
}

function readableError(error: unknown, fallback: string): string {
  const raw = String((error as { message?: unknown })?.message || '').trim()
  const jsonStart = raw.indexOf('{')
  if (jsonStart >= 0) {
    try {
      const payload = JSON.parse(raw.slice(jsonStart)) as { error?: unknown, message?: unknown }
      const detail = String(payload.error || payload.message || '').trim()
      if (detail) return detail
    } catch {}
  }
  return raw || fallback
}

function readableImportError(error: unknown, extension: string): string {
  const detail = readableError(error, copy.value.importFailed)
  const normalized = detail.toLowerCase()
  if (normalized.includes('50 mb') || normalized.includes('file_too_large')) {
    return copy.value.importTooLarge
  }
  if (
    normalized.includes('not a valid')
    || normalized.includes('damaged')
    || normalized.includes('expands beyond')
  ) {
    return copy.value.importInvalid.replace('{extension}', extension)
  }
  if (normalized.includes('only accepts')) {
    return copy.value.importTypeMismatch.replace('{extension}', extension)
  }
  return detail
}

function pause(milliseconds: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, milliseconds))
}

function clearLongRunningNotice(operationFormat: OfficeFormat) {
  const timer = longRunningTimers[operationFormat]
  if (timer !== undefined) window.clearTimeout(timer)
  delete longRunningTimers[operationFormat]
  formatTaskStates[operationFormat].longRunning = false
}

function startLongRunningNotice(operationFormat: OfficeFormat) {
  clearLongRunningNotice(operationFormat)
  longRunningTimers[operationFormat] = window.setTimeout(() => {
    const taskState = formatTaskStates[operationFormat]
    if (taskState.working) taskState.longRunning = true
    delete longRunningTimers[operationFormat]
  }, LONG_RUNNING_NOTICE_MS)
}

async function waitForOfficeOperation(
  initial: OfficeOperation,
  operationFormat: OfficeFormat,
): Promise<OfficeDocument | null> {
  const taskState = formatTaskStates[operationFormat]
  const runId = ++taskState.runId
  taskState.operation = initial
  let operation = initial
  let pollFailures = 0

  while (operation.status === 'queued' || operation.status === 'running') {
    await pause(650)
    if (runId !== taskState.runId) return null
    try {
      const response = await fetchOfficeOperation(operation.id)
      operation = response.operation
      taskState.operation = operation
      pollFailures = 0
    } catch (error) {
      pollFailures += 1
      if (pollFailures < 3) continue
      throw error
    }
  }

  if (operation.status === 'failed') {
    const errorTitle = operation.error
      ? (isChinese.value ? operation.error.title_zh : operation.error.title_en)
      : ''
    message.error(errorTitle || (operation.kind === 'create'
      ? copy.value.createFailed
      : copy.value.reviseFailed))
    return null
  }
  if (operation.status === 'needs_input') {
    if (format.value === operationFormat) await focusPromptInput()
    return null
  }
  if (operation.status === 'cancelled') return null
  if (!operation.document) throw new Error(copy.value.resultMissing)
  return operation.document
}

async function cancelActiveOperation() {
  const taskState = currentTaskState.value
  const operation = taskState.operation
  if (!operation || !canCancelOperation.value || cancelingOperation.value) return
  taskState.canceling = true
  try {
    const response = await cancelOfficeOperation(operation.id)
    taskState.operation = response.operation
    message.info(copy.value.cancelled)
  } catch (error) {
    message.error(readableError(error, copy.value.cancelFailed))
  } finally {
    taskState.canceling = false
  }
}

async function loadPreview() {
  const document = selectedDocument.value
  const runId = ++previewRunId
  previewHtml.value = ''
  previewError.value = ''
  if (!document || isCreateMode.value) {
    previewLoading.value = false
    return
  }

  previewLoading.value = true
  try {
    const html = await fetchOfficePreviewHtml(document.id)
    if (runId === previewRunId) previewHtml.value = html
  } catch (error) {
    if (runId === previewRunId) {
      previewError.value = readableError(error, copy.value.previewFailed)
    }
  } finally {
    if (runId === previewRunId) previewLoading.value = false
  }
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
  const operationFormat = format.value
  const taskState = formatTaskStates[operationFormat]
  const filesToModify = taskState.pendingFiles.slice()
  const createMode = isCreateMode.value
  const skillForRequest = selectedSkill.value
  const documentForRequest = selectedDocument.value
  if (createMode && !filesToModify.length && !skillForRequest) {
    message.error(copy.value.skillRequired)
    return
  }

  taskState.working = true
  taskState.importing = filesToModify.length > 0
  taskState.operation = null
  taskState.transportError = ''
  startLongRunningNotice(operationFormat)
  try {
    if (filesToModify.length) {
      const completedIds = new Set<string>()
      let lastDocument: OfficeDocument | null = null
      for (const pendingFile of filesToModify) {
        let importedDocument = pendingFile.importedDocument
        if (!importedDocument) {
          const imported = await importOfficeDocument(operationFormat, pendingFile.file)
          importedDocument = imported.document
          pendingFile.importedDocument = importedDocument
        }
        const response = await startOfficeRevisionOperation(importedDocument.id, cleanPrompt)
        const revisedDocument = await waitForOfficeOperation(response.operation, operationFormat)
        if (!revisedDocument) return
        upsertDocument(revisedDocument)
        lastDocument = revisedDocument
        completedIds.add(pendingFile.id)
        taskState.pendingFiles = taskState.pendingFiles.filter(item => !completedIds.has(item.id))
      }
      if (lastDocument) {
        taskState.selectedId = lastDocument.id
        taskState.creatingNew = false
        taskState.prompt = ''
        if (format.value === operationFormat) refreshPreview()
      }
      message.success(copy.value.filesRevised)
    } else if (createMode && skillForRequest) {
      const response = await startOfficeCreateOperation({
        format: operationFormat,
        skill_id: skillForRequest.id,
        prompt: cleanPrompt,
        title: title.value.trim() || undefined,
        language: language.value,
        ...(operationFormat === 'pptx'
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
      const document = await waitForOfficeOperation(response.operation, operationFormat)
      if (!document) return
      upsertDocument(document)
      taskState.selectedId = document.id
      taskState.creatingNew = false
      taskState.title = ''
      taskState.prompt = ''
      if (format.value === operationFormat) refreshPreview()
      message.success(copy.value.created)
    } else if (documentForRequest) {
      const response = await startOfficeRevisionOperation(documentForRequest.id, cleanPrompt)
      const document = await waitForOfficeOperation(response.operation, operationFormat)
      if (!document) return
      upsertDocument(document)
      taskState.selectedId = document.id
      taskState.creatingNew = false
      taskState.prompt = ''
      if (format.value === operationFormat) refreshPreview()
      message.success(copy.value.revised)
    }
  } catch (error) {
    const fallback = createMode && !filesToModify.length ? copy.value.createFailed : copy.value.reviseFailed
    taskState.transportError = filesToModify.length
      ? readableImportError(error, `.${operationFormat}`)
      : readableError(error, fallback)
    const currentOperation = taskState.operation
    if (currentOperation) {
      taskState.operation = Object.assign({}, currentOperation, { status: 'failed' as const })
    }
    message.error(taskState.transportError)
  } finally {
    clearLongRunningNotice(operationFormat)
    taskState.working = false
    taskState.importing = false
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
}, { immediate: true })

watch([format, skills], () => {
  if (selectedSkill.value) return
  const first = currentSkills.value[0]
  selectedSkillId.value = first?.id || ''
  applySkillDefaults(first || null)
})

watch(
  [() => selectedDocument.value?.id, previewVersion],
  loadPreview,
)

onMounted(loadOffice)
onBeforeUnmount(() => {
  previewRunId += 1
  for (const operationFormat of Object.keys(longRunningTimers) as OfficeFormat[]) {
    const timer = longRunningTimers[operationFormat]
    if (timer !== undefined) window.clearTimeout(timer)
  }
})
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
            <section v-if="pendingFiles.length" class="pending-files" :aria-label="copy.pendingFiles">
              <div
                v-for="pendingFile in pendingFiles"
                :key="pendingFile.id"
                class="pending-file"
              >
                <span class="pending-file-icon" :class="format">{{ currentFormat.mark }}</span>
                <span class="pending-file-copy">
                  <strong>{{ pendingFile.file.name }}</strong>
                  <small>{{ formatFileSize(pendingFile.file.size) }}</small>
                </span>
                <button
                  type="button"
                  class="pending-file-remove"
                  :aria-label="copy.removeFile"
                  :title="copy.removeFile"
                  :disabled="working"
                  @click="removePendingFile(pendingFile.id)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                    <path d="M6 6l12 12M18 6L6 18" />
                  </svg>
                </button>
              </div>
            </section>

            <label class="field instruction-field">
              <span>{{ copy.workflowInput }}</span>
              <NInput
                ref="promptInputRef"
                v-model:value="prompt"
                type="textarea"
                :placeholder="localizedSkillValue(selectedSkill, 'placeholder')"
                :autosize="{ minRows: 12, maxRows: 22 }"
                :maxlength="30000"
                show-count
              />
            </label>

            <section v-if="activeOperation || operationTransportError" class="operation-activity">
              <header class="activity-header">
                <strong>{{ copy.activity }}</strong>
                <div class="activity-actions">
                  <span :class="['activity-status', activeOperation?.status || 'failed']">
                    {{ operationTransportError && !activeOperation ? copy.failed : operationStatusText }}
                  </span>
                  <NButton
                    v-if="canCancelOperation"
                    size="tiny"
                    secondary
                    type="error"
                    attr-type="button"
                    :loading="cancelingOperation"
                    @click="cancelActiveOperation"
                  >
                    {{ cancelingOperation ? copy.cancelling : copy.cancelTask }}
                  </NButton>
                </div>
              </header>
              <div v-if="activeOperation" class="activity-progress" role="progressbar" :aria-valuenow="activeOperation.percent" aria-valuemin="0" aria-valuemax="100">
                <span :style="{ width: `${activeOperation.percent}%` }" />
              </div>
              <ol v-if="activeOperation?.events.length" class="activity-list">
                <li
                  v-for="(event, index) in activeOperation.events"
                  :key="event.stage"
                  :class="{
                    done: activeOperation.status === 'completed' || index < activeOperation.events.length - 1,
                    current: activeOperation.status === 'running' && index === activeOperation.events.length - 1,
                    needsInput: event.stage === 'needs_input',
                    failed: event.stage === 'failed',
                    cancelled: event.stage === 'cancelled',
                  }"
                >
                  <span class="activity-dot" />
                  <span>{{ localizedProgress(event) }}</span>
                  <small>{{ event.percent }}%</small>
                </li>
              </ol>
              <p v-else-if="activeOperation" class="activity-waiting">{{ copy.waitingForProgress }}</p>
              <p v-if="longRunning && canCancelOperation" class="operation-long-running" role="status">
                {{ copy.longRunningNotice }}
              </p>
              <div v-if="activeOperation?.clarification" class="operation-clarification" role="status">
                <strong>{{ localizedOperationClarification('title') }}</strong>
                <p>{{ localizedOperationClarification('message') }}</p>
                <p><b>{{ copy.clarificationExample }}:</b> {{ localizedOperationClarification('example') }}</p>
              </div>
              <div v-else-if="activeOperation?.error" class="operation-error">
                <strong>{{ localizedOperationError('title') }}</strong>
                <p>{{ localizedOperationError('message') }}</p>
                <p><b>{{ copy.suggestion }}:</b> {{ localizedOperationError('suggestion') }}</p>
                <details v-if="activeOperation.error.technical_detail">
                  <summary>{{ copy.technicalDetail }}</summary>
                  <pre>{{ activeOperation.error.technical_detail }}</pre>
                </details>
              </div>
              <div v-else-if="operationTransportError" class="operation-error">
                <strong>{{ copy.failed }}</strong>
                <p>{{ operationTransportError }}</p>
              </div>
            </section>

            <div class="form-actions">
              <input
                ref="officeFileInputRef"
                class="office-file-input"
                type="file"
                multiple
                :accept="officeImportAccept"
                @change="handleOfficeImport"
              >
              <NButton
                attr-type="button"
                size="large"
                secondary
                :disabled="working"
                @click="openOfficeImportPicker"
              >
                {{ copy.importFile }}
              </NButton>
              <NButton
                type="primary"
                attr-type="submit"
                size="large"
                :loading="working"
                :disabled="!prompt.trim() || (!pendingFiles.length && !selectedSkill) || !servicesReady"
              >
                {{ working
                  ? (importing ? copy.modifyingFiles : copy.generating)
                  : (pendingFiles.length ? copy.modifyFiles : copy.generate) }}
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
            <div v-else-if="previewError" class="preview-error">
              <strong>{{ copy.previewFailed }}</strong>
              <p>{{ previewError }}</p>
              <NButton size="small" secondary @click="refreshPreview">{{ copy.retry }}</NButton>
            </div>
            <iframe
              v-else-if="previewHtml"
              :key="`${selectedDocument?.id}-${previewVersion}`"
              :srcdoc="previewHtml"
              :title="selectedDocument?.file_name || copy.preview"
              class="office-preview-frame"
              sandbox="allow-scripts"
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
                ref="promptInputRef"
                v-model:value="prompt"
                type="textarea"
                :placeholder="copy.revisePlaceholder"
                :autosize="{ minRows: 12, maxRows: 22 }"
                :maxlength="30000"
                show-count
              />
            </label>
            <section v-if="activeOperation || operationTransportError" class="operation-activity">
              <header class="activity-header">
                <strong>{{ copy.activity }}</strong>
                <div class="activity-actions">
                  <span :class="['activity-status', activeOperation?.status || 'failed']">
                    {{ operationTransportError && !activeOperation ? copy.failed : operationStatusText }}
                  </span>
                  <NButton
                    v-if="canCancelOperation"
                    size="tiny"
                    secondary
                    type="error"
                    attr-type="button"
                    :loading="cancelingOperation"
                    @click="cancelActiveOperation"
                  >
                    {{ cancelingOperation ? copy.cancelling : copy.cancelTask }}
                  </NButton>
                </div>
              </header>
              <div v-if="activeOperation" class="activity-progress" role="progressbar" :aria-valuenow="activeOperation.percent" aria-valuemin="0" aria-valuemax="100">
                <span :style="{ width: `${activeOperation.percent}%` }" />
              </div>
              <ol v-if="activeOperation?.events.length" class="activity-list">
                <li
                  v-for="(event, index) in activeOperation.events"
                  :key="event.stage"
                  :class="{
                    done: activeOperation.status === 'completed' || index < activeOperation.events.length - 1,
                    current: activeOperation.status === 'running' && index === activeOperation.events.length - 1,
                    needsInput: event.stage === 'needs_input',
                    failed: event.stage === 'failed',
                    cancelled: event.stage === 'cancelled',
                  }"
                >
                  <span class="activity-dot" />
                  <span>{{ localizedProgress(event) }}</span>
                  <small>{{ event.percent }}%</small>
                </li>
              </ol>
              <p v-else-if="activeOperation" class="activity-waiting">{{ copy.waitingForProgress }}</p>
              <p v-if="longRunning && canCancelOperation" class="operation-long-running" role="status">
                {{ copy.longRunningNotice }}
              </p>
              <div v-if="activeOperation?.clarification" class="operation-clarification" role="status">
                <strong>{{ localizedOperationClarification('title') }}</strong>
                <p>{{ localizedOperationClarification('message') }}</p>
                <p><b>{{ copy.clarificationExample }}:</b> {{ localizedOperationClarification('example') }}</p>
              </div>
              <div v-else-if="activeOperation?.error" class="operation-error">
                <strong>{{ localizedOperationError('title') }}</strong>
                <p>{{ localizedOperationError('message') }}</p>
                <p><b>{{ copy.suggestion }}:</b> {{ localizedOperationError('suggestion') }}</p>
                <details v-if="activeOperation.error.technical_detail">
                  <summary>{{ copy.technicalDetail }}</summary>
                  <pre>{{ activeOperation.error.technical_detail }}</pre>
                </details>
              </div>
              <div v-else-if="operationTransportError" class="operation-error">
                <strong>{{ copy.failed }}</strong>
                <p>{{ operationTransportError }}</p>
              </div>
            </section>
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

.pending-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.pending-file {
  position: relative;
  width: 152px;
  min-height: 78px;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  padding: 11px 26px 11px 11px;
  border: 1px solid $border-color;
  border-radius: 8px;
  background: $bg-secondary;
}

.pending-file-icon {
  width: 28px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 4px;
  color: #fff;
  background: #2563eb;
  font-size: 11px;
  font-weight: 750;
}

.pending-file-icon.xlsx { background: #15803d; }
.pending-file-icon.pptx { background: #c2410c; }

.pending-file-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.pending-file-copy strong,
.pending-file-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pending-file-copy strong { font-size: 10px; font-weight: 620; }
.pending-file-copy small { color: $text-muted; font-size: 9px; }

.pending-file-remove {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  color: $text-muted;
  background: transparent;
  cursor: pointer;
}

.pending-file-remove:hover:not(:disabled) {
  color: $text-primary;
  background: rgba(127, 127, 127, .15);
}

.pending-file-remove:disabled { cursor: default; opacity: .45; }

.form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 4px;
}

.office-file-input { display: none; }

.operation-activity {
  min-width: 0;
  padding: 14px 0;
  border-top: 1px solid $border-color;
  border-bottom: 1px solid $border-color;
}

.activity-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.activity-header strong {
  font-size: 12px;
}

.activity-actions {
  display: flex;
  align-items: center;
  gap: 9px;
}

.activity-status {
  color: $text-muted;
  font-size: 10px;
  font-weight: 650;
}

.activity-status.running { color: #1d4ed8; }
.activity-status.needs_input { color: #a16207; }
.activity-status.completed { color: #047857; }
.activity-status.failed { color: #b91c1c; }
.activity-status.cancelled { color: #64748b; }

.activity-progress {
  height: 4px;
  overflow: hidden;
  background: $bg-secondary;
}

.activity-progress > span {
  height: 100%;
  display: block;
  background: #2563eb;
  transition: width .25s ease;
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.activity-list li {
  position: relative;
  min-width: 0;
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) auto;
  align-items: start;
  gap: 8px;
  padding: 5px 0;
  color: $text-muted;
  font-size: 11px;
  line-height: 1.45;
}

.activity-list li::before {
  content: '';
  position: absolute;
  top: 18px;
  bottom: -6px;
  left: 4px;
  width: 1px;
  background: $border-color;
}

.activity-list li:last-child::before { display: none; }

.activity-list li.done,
.activity-list li.current { color: $text-secondary; }
.activity-list li.needsInput { color: #854d0e; }
.activity-list li.failed { color: #b91c1c; }
.activity-list li.cancelled { color: #64748b; }

.activity-dot {
  width: 9px;
  height: 9px;
  display: block;
  margin-top: 3px;
  border: 2px solid #94a3b8;
  border-radius: 50%;
  background: $bg-card;
}

.activity-list li.done .activity-dot {
  border-color: #059669;
  background: #059669;
}

.activity-list li.current .activity-dot {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, .12);
}

.activity-list li.needsInput .activity-dot {
  border-color: #ca8a04;
  background: #facc15;
}

.activity-list li.failed .activity-dot {
  border-color: #dc2626;
  background: #dc2626;
}

.activity-list li.cancelled .activity-dot {
  border-color: #64748b;
  background: #64748b;
}

.activity-list small {
  color: $text-muted;
  font-size: 9px;
  font-variant-numeric: tabular-nums;
}

.activity-waiting {
  margin: 12px 0 0;
  color: $text-muted;
  font-size: 11px;
}

.operation-long-running {
  margin: 12px 0 0;
  padding: 9px 11px;
  border-left: 3px solid #ca8a04;
  color: #854d0e;
  background: rgba(254, 249, 195, .42);
  font-size: 11px;
  line-height: 1.5;
}

.operation-error,
.operation-clarification {
  margin-top: 12px;
  padding: 11px 12px;
  font-size: 11px;
  line-height: 1.5;
}

.operation-clarification {
  border-left: 3px solid #ca8a04;
  background: rgba(254, 249, 195, .5);
  color: #713f12;
}

.operation-clarification p { margin: 4px 0 0; }

.operation-error {
  border-left: 3px solid #dc2626;
  background: rgba(254, 226, 226, .42);
  color: #991b1b;
}

.operation-error p { margin: 4px 0 0; }
.operation-error details { margin-top: 7px; }
.operation-error summary { cursor: pointer; font-weight: 600; }
.operation-error pre {
  max-height: 130px;
  overflow: auto;
  margin: 7px 0 0;
  padding: 8px;
  color: #7f1d1d;
  background: rgba(255, 255, 255, .58);
  font: 10px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  word-break: break-word;
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

.preview-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 9px;
  padding: 28px;
  color: #991b1b;
  background: #f8fafc;
  text-align: center;
}

.preview-error strong { font-size: 13px; }
.preview-error p {
  max-width: 520px;
  margin: 0;
  color: #6b7280;
  font-size: 11px;
  line-height: 1.55;
  word-break: break-word;
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
