<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSpin, NTag } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import {
  fetchOfficePreviewHtml,
  type OfficeDocument,
} from '@/api/reins/office'
import { downloadFile } from '@/api/reins/download'

defineEmits<{ close: [] }>()
const props = defineProps<{ document: OfficeDocument }>()

const { locale } = useI18n()
const previewLoading = ref(true)
const previewVersion = ref(0)
const previewHtml = ref('')
const previewError = ref('')

const isChinese = computed(() => locale.value.toLowerCase().startsWith('zh'))
const copy = computed(() => isChinese.value
  ? {
      title: '预览',
      officeDocument: 'Office 文档',
      refresh: '刷新',
      download: '下载',
      failed: '无法加载预览',
    }
  : {
      title: 'Preview',
      officeDocument: 'Office document',
      refresh: 'Refresh',
      download: 'Download',
      failed: 'Unable to load preview',
    })

async function loadPreview() {
  previewLoading.value = true
  previewError.value = ''
  previewHtml.value = ''
  try {
    previewHtml.value = await fetchOfficePreviewHtml(props.document.id)
  } catch (error) {
    previewError.value = error instanceof Error ? error.message : copy.value.failed
    previewLoading.value = false
  }
}

function refreshPreview() {
  previewVersion.value += 1
  void loadPreview()
}

async function downloadSelected() {
  await downloadFile(props.document.path, props.document.file_name)
}

watch(
  () => [props.document.id, props.document.updated_at],
  () => { void loadPreview() },
  { immediate: true },
)
</script>

<template>
  <aside class="office-preview-panel">
    <header class="office-preview-header">
      <div class="office-preview-heading">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M9 3v18" />
        </svg>
        <strong>{{ copy.title }}</strong>
      </div>
      <div class="office-preview-header-actions">
        <button type="button" :title="copy.refresh" @click="refreshPreview">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M20 12a8 8 0 1 1-2.34-5.66L20 8.68M20 4v4.68h-4.68" /></svg>
        </button>
        <button type="button" aria-label="Close preview" @click="$emit('close')">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="m18 6-12 12M6 6l12 12" /></svg>
        </button>
      </div>
    </header>

    <section class="office-document-browser">
      <div class="office-document-section-title">
        <span>{{ copy.officeDocument }}</span>
        <span>1</span>
      </div>
      <div class="office-document-tabs">
        <button type="button" class="active">
          <span class="format-dot" :class="document.kind">{{ document.kind.charAt(0).toUpperCase() }}</span>
          <span>{{ document.title }}</span>
        </button>
      </div>
    </section>

    <section class="office-preview-canvas">
      <div class="document-toolbar">
        <div>
          <strong>{{ document.title }}</strong>
          <NTag size="small" :bordered="false">{{ document.kind.toUpperCase() }}</NTag>
        </div>
        <NButton quaternary size="tiny" @click="downloadSelected">{{ copy.download }}</NButton>
      </div>
      <div class="preview-shell">
        <div v-if="previewLoading" class="preview-loading"><NSpin size="small" /></div>
        <div v-else-if="previewError" class="preview-error">
          <strong>{{ copy.failed }}</strong>
          <span>{{ previewError }}</span>
          <NButton size="small" secondary @click="refreshPreview">{{ copy.refresh }}</NButton>
        </div>
        <iframe
          v-if="previewHtml"
          :key="`${document.id}-${previewVersion}`"
          :srcdoc="previewHtml"
          :title="document.file_name"
          sandbox="allow-scripts"
          @load="previewLoading = false"
        />
      </div>
    </section>
  </aside>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.office-preview-panel {
  width: clamp(340px, 31vw, 520px);
  height: 100%;
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  min-width: 0;
  overflow: hidden;
  background: $bg-card;
  border-left: 1px solid $border-color;
}

.office-preview-header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: 0 0 64px;
  padding: 0 18px;
  border-bottom: 1px solid $border-color;
}

.office-preview-heading,
.office-preview-header-actions,
.office-document-section-title,
.document-toolbar,
.document-toolbar > div {
  display: flex;
  align-items: center;
}

.office-preview-heading { gap: 9px; }
.office-preview-heading strong { font-size: 14px; }
.office-preview-header-actions { gap: 4px; }

.office-preview-header-actions button {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 8px;
  color: $text-muted;
  background: transparent;
  cursor: pointer;
}

.office-preview-header-actions button:hover { color: $text-primary; background: $bg-secondary; }

.office-document-browser {
  flex: 0 0 auto;
  padding: 14px 16px 10px;
  border-bottom: 1px solid $border-color;
}

.office-document-section-title {
  justify-content: space-between;
  color: $text-muted;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: .04em;
  text-transform: uppercase;
}

.office-document-tabs {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  overflow-x: auto;
  scrollbar-width: none;
}

.office-document-tabs::-webkit-scrollbar { display: none; }

.office-document-tabs button {
  max-width: 190px;
  height: 32px;
  display: flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
  padding: 0 10px;
  border: 1px solid $border-color;
  border-radius: 9px;
  color: $text-secondary;
  background: $bg-primary;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.office-document-tabs button > span:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.office-document-tabs button.active { color: $text-primary; border-color: $text-muted; background: $bg-card; }

.format-dot {
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  flex: 0 0 18px;
  border-radius: 5px;
  color: #fff;
  background: #2563eb;
  font-size: 9px;
  font-weight: 700;
}

.format-dot.xlsx { background: #16803d; }
.format-dot.pptx { background: #c2410c; }

.office-preview-canvas {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: $bg-secondary;
}

.office-preview-loading,
.office-preview-empty,
.preview-loading,
.preview-error {
  display: grid;
  place-items: center;
}

.office-preview-loading { position: absolute; inset: 0; }

.office-preview-empty {
  flex: 1;
  align-content: center;
  padding: 32px;
  text-align: center;
}

.empty-icon {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  margin-bottom: 14px;
  border-radius: 18px;
  color: $text-muted;
  background: $bg-card;
  border: 1px solid $border-color;
}

.office-preview-empty strong { font-size: 14px; }
.office-preview-empty p { max-width: 250px; margin: 6px 0 16px; color: $text-muted; font-size: 12px; line-height: 1.5; }

.document-toolbar {
  height: 48px;
  justify-content: space-between;
  flex: 0 0 48px;
  padding: 0 12px 0 16px;
  background: $bg-card;
  border-bottom: 1px solid $border-color;
}

.document-toolbar > div { min-width: 0; gap: 8px; }
.document-toolbar strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }

.preview-shell { position: relative; flex: 1; min-height: 0; }
.preview-shell iframe { width: 100%; height: 100%; display: block; border: 0; background: #fff; }
.preview-loading { position: absolute; inset: 0; z-index: 1; background: rgba(245, 245, 245, .8); }

.preview-error {
  position: absolute;
  inset: 0;
  align-content: center;
  gap: 8px;
  padding: 24px;
  color: $text-muted;
  text-align: center;
  background: $bg-secondary;
}

.preview-error strong { color: $text-primary; font-size: 13px; }
.preview-error span { max-width: 320px; overflow-wrap: anywhere; font-size: 11px; }

@media (max-width: 1180px) {
  .office-preview-panel { width: 360px; }
}

@media (max-width: 940px) {
  .office-preview-panel {
    position: absolute;
    inset: 0 0 0 auto;
    z-index: 90;
    width: min(520px, 92vw);
    box-shadow: -16px 0 40px rgba(0, 0, 0, .12);
  }
}
</style>
