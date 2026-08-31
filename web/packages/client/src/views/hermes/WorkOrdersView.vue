<script setup lang="ts">
import {
  computed,
  h,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'
import {
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NInput,
  NSelect,
  NSpin,
  NTag,
  useMessage,
  type DataTableColumns,
  type SelectOption,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import {
  downloadWorkOrdersExcel,
  fetchWorkOrder,
  fetchWorkOrderSummary,
  fetchWorkOrders,
  type WorkOrderRecord,
  type WorkOrderSummary,
} from '@/api/hermes/work-orders'

const { t } = useI18n()
const message = useMessage()

const summary = ref<WorkOrderSummary | null>(null)
const records = ref<WorkOrderRecord[]>([])
const total = ref(0)
const loading = ref(false)
const exporting = ref(false)
const detailLoading = ref(false)
const selectedRecord = ref<WorkOrderRecord | null>(null)
const drawerOpen = ref(false)

const search = ref('')
const status = ref('')
const priority = ref('')
const role = ref('')
const category = ref('')
const notificationStatus = ref('')
const page = ref(1)
const pageSize = ref(25)

let refreshTimer: ReturnType<typeof setInterval> | null = null
let searchTimer: ReturnType<typeof setTimeout> | null = null
let requestSequence = 0

const statusTranslationKeys: Record<string, string> = {
  new: 'workOrders.status.new',
  open: 'workOrders.status.open',
  pending_notification: 'workOrders.status.pendingNotification',
  waiting_human_review: 'workOrders.status.waitingHumanReview',
  notified: 'workOrders.status.notified',
  processing: 'workOrders.status.processing',
  resolved: 'workOrders.status.resolved',
  closed: 'workOrders.status.closed',
  failed: 'workOrders.status.failed',
}

const priorityTranslationKeys: Record<string, string> = {
  high: 'workOrders.priority.high',
  urgent: 'workOrders.priority.high',
  critical: 'workOrders.priority.high',
  emergency: 'workOrders.priority.high',
  normal: 'workOrders.priority.normal',
  medium: 'workOrders.priority.normal',
  low: 'workOrders.priority.low',
}

const notificationTranslationKeys: Record<string, string> = {
  sent: 'workOrders.notification.sent',
  dry_run: 'workOrders.notification.dryRun',
  pending_configuration: 'workOrders.notification.pendingConfiguration',
  skipped_duplicate: 'workOrders.notification.skippedDuplicate',
  failed: 'workOrders.notification.failed',
  disabled: 'workOrders.notification.disabled',
}

function translated(
  value: string,
  keys: Record<string, string>,
  emptyKey: string,
): string {
  const normalized = value.toLocaleLowerCase()
  const key = keys[normalized]
  return key ? t(key) : value || t(emptyKey)
}

function statusLabel(value: string): string {
  return translated(value, statusTranslationKeys, 'workOrders.labels.unknown')
}

function priorityLabel(value: string): string {
  return translated(value, priorityTranslationKeys, 'workOrders.labels.unknown')
}

function notificationLabel(value: string): string {
  return translated(
    value,
    notificationTranslationKeys,
    'workOrders.labels.notSent',
  )
}

function formatDateTime(value: string): string {
  if (!value) return t('workOrders.labels.empty')
  if (value.includes('T')) {
    const parsed = new Date(value)
    if (!Number.isNaN(parsed.getTime())) {
      return new Intl.DateTimeFormat(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(parsed)
    }
  }
  return value.replace('T', ' ').slice(0, 16)
}

function statusTagType(
  value: string,
): 'default' | 'success' | 'warning' | 'error' | 'info' {
  if (['resolved', 'closed'].includes(value)) return 'success'
  if (value === 'processing') return 'info'
  if (['failed', 'waiting_human_review'].includes(value)) return 'error'
  if (['new', 'open', 'pending_notification'].includes(value)) return 'warning'
  return 'default'
}

function notificationTagType(
  value: string,
): 'default' | 'success' | 'warning' | 'error' | 'info' {
  if (['sent', 'skipped_duplicate'].includes(value)) return 'success'
  if (value === 'dry_run') return 'info'
  if (value === 'pending_configuration') return 'warning'
  if (value === 'failed') return 'error'
  return 'default'
}

function renderTag(
  label: string,
  type: 'default' | 'success' | 'warning' | 'error' | 'info',
) {
  return h(
    NTag,
    {
      size: 'small',
      type,
      bordered: false,
      round: false,
    },
    { default: () => label },
  )
}

async function loadWorkOrders(options: { silent?: boolean } = {}) {
  const sequence = ++requestSequence
  if (!options.silent) loading.value = true
  try {
    const [nextSummary, response] = await Promise.all([
      fetchWorkOrderSummary(),
      fetchWorkOrders({
        search: search.value,
        status: status.value,
        priority: priority.value,
        role: role.value,
        category: category.value,
        notification_status: notificationStatus.value,
        limit: pageSize.value,
        offset: (page.value - 1) * pageSize.value,
      }),
    ])
    if (sequence !== requestSequence) return
    summary.value = nextSummary
    records.value = response.records
    total.value = response.total
  } catch (error: any) {
    if (sequence === requestSequence && !options.silent) {
      message.error(error?.message || t('workOrders.loadFailed'))
    }
  } finally {
    if (sequence === requestSequence) loading.value = false
  }
}

function reloadFromFirstPage() {
  page.value = 1
  void loadWorkOrders()
}

function clearFilters() {
  search.value = ''
  status.value = ''
  priority.value = ''
  role.value = ''
  category.value = ''
  notificationStatus.value = ''
  reloadFromFirstPage()
}

async function openRecord(record: WorkOrderRecord) {
  selectedRecord.value = record
  drawerOpen.value = true
  detailLoading.value = true
  try {
    selectedRecord.value = await fetchWorkOrder(record.id)
  } catch (error: any) {
    message.error(error?.message || t('workOrders.detailFailed'))
  } finally {
    detailLoading.value = false
  }
}

async function exportWorkbook() {
  exporting.value = true
  try {
    await downloadWorkOrdersExcel()
    message.success(t('workOrders.exportSuccess'))
  } catch (error: any) {
    message.error(error?.message || t('workOrders.exportFailed'))
  } finally {
    exporting.value = false
  }
}

function optionsFromValues(
  values: string[],
  label: (value: string) => string = (value) => value,
): SelectOption[] {
  return values.map((value) => ({ value, label: label(value) }))
}

const statusOptions = computed(() =>
  optionsFromValues(summary.value?.filters.statuses || [], statusLabel),
)
const priorityOptions = computed(() =>
  optionsFromValues(summary.value?.filters.priorities || [], priorityLabel),
)
const categoryOptions = computed(() =>
  optionsFromValues(summary.value?.filters.categories || []),
)
const notificationOptions = computed(() =>
  optionsFromValues(
    summary.value?.filters.notification_statuses || [],
    notificationLabel,
  ),
)
const roleOptions = computed<SelectOption[]>(() =>
  (summary.value?.filters.roles || []).map((item) => ({
    value: item.value,
    label: item.label,
  })),
)

const metrics = computed(() => [
  {
    label: t('workOrders.stats.total'),
    value: summary.value?.total || 0,
    alert: false,
  },
  {
    label: t('workOrders.stats.pending'),
    value: summary.value?.pending || 0,
    alert: false,
  },
  {
    label: t('workOrders.stats.processing'),
    value: summary.value?.processing || 0,
    alert: false,
  },
  {
    label: t('workOrders.stats.urgent'),
    value: summary.value?.urgent || 0,
    alert: false,
  },
  {
    label: t('workOrders.stats.notificationFailed'),
    value: summary.value?.notification_failed || 0,
    alert: (summary.value?.notification_failed || 0) > 0,
  },
  {
    label: t('workOrders.stats.completed'),
    value: summary.value?.completed || 0,
    alert: false,
  },
])

const columns = computed<DataTableColumns<WorkOrderRecord>>(() => [
  {
    title: t('workOrders.table.ticket'),
    key: 'external_id',
    width: 184,
    fixed: 'left',
    ellipsis: { tooltip: true },
    render: (row) => h('span', { class: 'ticket-id mono' }, row.external_id),
  },
  {
    title: t('workOrders.table.createdAt'),
    key: 'created_at',
    width: 148,
    render: (row) => formatDateTime(row.created_at),
  },
  {
    title: t('workOrders.table.status'),
    key: 'status',
    width: 108,
    render: (row) =>
      renderTag(statusLabel(row.status), statusTagType(row.status)),
  },
  {
    title: t('workOrders.table.priority'),
    key: 'priority',
    width: 86,
    render: (row) =>
      renderTag(
        priorityLabel(row.priority),
        ['high', 'urgent', 'critical', 'emergency'].includes(row.priority)
          ? 'error'
          : 'default',
      ),
  },
  {
    title: t('workOrders.table.category'),
    key: 'category',
    width: 150,
    ellipsis: { tooltip: true },
  },
  {
    title: t('workOrders.table.department'),
    key: 'assigned_role_label',
    width: 126,
    ellipsis: { tooltip: true },
  },
  {
    title: t('workOrders.table.assignee'),
    key: 'assignees',
    width: 164,
    ellipsis: { tooltip: true },
    render: (row) =>
      row.assignees.join('、') || t('workOrders.labels.unassigned'),
  },
  {
    title: t('workOrders.table.location'),
    key: 'location',
    width: 174,
    ellipsis: { tooltip: true },
  },
  {
    title: t('workOrders.table.issue'),
    key: 'issue',
    width: 340,
    render: (row) =>
      h(
        'span',
        { class: 'issue-cell', title: row.issue },
        row.issue || t('workOrders.labels.empty'),
      ),
  },
  {
    title: t('workOrders.table.notification'),
    key: 'notification_status',
    width: 118,
    render: (row) =>
      renderTag(
        notificationLabel(row.notification_status),
        notificationTagType(row.notification_status),
      ),
  },
  {
    title: t('workOrders.table.updatedAt'),
    key: 'updated_at',
    width: 148,
    render: (row) => formatDateTime(row.updated_at),
  },
])

const pagination = computed(() => ({
  page: page.value,
  pageSize: pageSize.value,
  itemCount: total.value,
  showSizePicker: true,
  pageSizes: [20, 25, 50, 100],
  onUpdatePage: (value: number) => {
    page.value = value
    void loadWorkOrders()
  },
  onUpdatePageSize: (value: number) => {
    pageSize.value = value
    page.value = 1
    void loadWorkOrders()
  },
}))

watch([status, priority, role, category, notificationStatus], () => {
  reloadFromFirstPage()
})

watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(reloadFromFirstPage, 300)
})

onMounted(() => {
  void loadWorkOrders()
  refreshTimer = setInterval(() => {
    void loadWorkOrders({ silent: true })
  }, 30_000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <div class="work-orders-page">
    <header class="page-header work-orders-header">
      <div>
        <h1 class="header-title">{{ t('workOrders.title') }}</h1>
        <div class="header-meta">
          <span>
            {{ t('workOrders.lastUpdated') }}:
            {{ formatDateTime(summary?.last_updated || '') }}
          </span>
          <span v-if="summary?.export.visible_path" class="export-path mono">
            {{ summary.export.visible_path }}
          </span>
        </div>
      </div>
      <div class="header-actions">
        <NButton
          secondary
          :loading="loading"
          @click="loadWorkOrders()"
        >
          <template #icon>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M20 6v5h-5" />
              <path d="M4 18v-5h5" />
              <path d="M18.5 9A7 7 0 0 0 6.3 6.3L4 8" />
              <path d="M5.5 15A7 7 0 0 0 17.7 17.7L20 16" />
            </svg>
          </template>
          {{ t('workOrders.actions.refresh') }}
        </NButton>
        <NButton
          type="primary"
          :loading="exporting"
          :disabled="!summary?.export.available"
          @click="exportWorkbook"
        >
          <template #icon>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M12 3v12" />
              <path d="m7 10 5 5 5-5" />
              <path d="M5 21h14" />
            </svg>
          </template>
          {{ t('workOrders.actions.exportExcel') }}
        </NButton>
      </div>
    </header>

    <section class="metric-strip" aria-label="Work order summary">
      <div
        v-for="metric in metrics"
        :key="metric.label"
        class="metric"
        :class="{ alert: metric.alert }"
      >
        <span class="metric-label">{{ metric.label }}</span>
        <strong class="metric-value">{{ metric.value }}</strong>
      </div>
    </section>

    <section class="filter-band">
      <NInput
        v-model:value="search"
        clearable
        class="search-input"
        :placeholder="t('workOrders.filters.searchPlaceholder')"
      />
      <NSelect
        v-model:value="status"
        clearable
        :options="statusOptions"
        :placeholder="t('workOrders.filters.status')"
      />
      <NSelect
        v-model:value="priority"
        clearable
        :options="priorityOptions"
        :placeholder="t('workOrders.filters.priority')"
      />
      <NSelect
        v-model:value="role"
        clearable
        :options="roleOptions"
        :placeholder="t('workOrders.filters.department')"
      />
      <NSelect
        v-model:value="category"
        clearable
        filterable
        :options="categoryOptions"
        :placeholder="t('workOrders.filters.category')"
      />
      <NSelect
        v-model:value="notificationStatus"
        clearable
        :options="notificationOptions"
        :placeholder="t('workOrders.filters.notification')"
      />
      <NButton quaternary @click="clearFilters">
        <template #icon>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </template>
        {{ t('workOrders.actions.clearFilters') }}
      </NButton>
    </section>

    <section class="table-band">
      <NSpin :show="loading">
        <NDataTable
          v-if="summary?.database_exists"
          remote
          :columns="columns"
          :data="records"
          :pagination="pagination"
          :row-key="(row: WorkOrderRecord) => row.id"
          :row-props="(row: WorkOrderRecord) => ({
            class: 'clickable-row',
            onClick: () => openRecord(row),
          })"
          :scroll-x="1720"
          :bordered="false"
          size="small"
        />
        <NEmpty
          v-else
          class="empty-state"
          :description="t('workOrders.states.noDatabase')"
        />
      </NSpin>
    </section>

    <NDrawer
      v-model:show="drawerOpen"
      :width="'min(620px, 100vw)'"
      placement="right"
    >
      <NDrawerContent
        :title="selectedRecord?.external_id || t('workOrders.detail.title')"
        closable
      >
        <NSpin :show="detailLoading">
          <article v-if="selectedRecord" class="ticket-detail">
            <div class="detail-status-row">
              <NTag
                size="small"
                :type="statusTagType(selectedRecord.status)"
                :bordered="false"
                :round="false"
              >
                {{ statusLabel(selectedRecord.status) }}
              </NTag>
              <NTag
                size="small"
                :type="['high', 'urgent', 'critical', 'emergency'].includes(selectedRecord.priority) ? 'error' : 'default'"
                :bordered="false"
                :round="false"
              >
                {{ priorityLabel(selectedRecord.priority) }}
              </NTag>
            </div>

            <dl class="detail-grid">
              <div>
                <dt>{{ t('workOrders.detail.category') }}</dt>
                <dd>{{ selectedRecord.category || t('workOrders.labels.empty') }}</dd>
              </div>
              <div>
                <dt>{{ t('workOrders.detail.department') }}</dt>
                <dd>{{ selectedRecord.assigned_role_label || t('workOrders.labels.unassigned') }}</dd>
              </div>
              <div v-if="selectedRecord.assignees.length > 0">
                <dt>{{ t('workOrders.detail.assignee') }}</dt>
                <dd>{{ selectedRecord.assignees.join('、') || t('workOrders.labels.unassigned') }}</dd>
              </div>
              <div>
                <dt>{{ t('workOrders.detail.location') }}</dt>
                <dd>{{ selectedRecord.location || t('workOrders.labels.empty') }}</dd>
              </div>
              <div>
                <dt>{{ t('workOrders.detail.createdAt') }}</dt>
                <dd>{{ formatDateTime(selectedRecord.created_at) }}</dd>
              </div>
              <div>
                <dt>{{ t('workOrders.detail.updatedAt') }}</dt>
                <dd>{{ formatDateTime(selectedRecord.updated_at) }}</dd>
              </div>
            </dl>

            <section class="detail-section">
              <h2>{{ t('workOrders.detail.issue') }}</h2>
              <p>{{ selectedRecord.issue || t('workOrders.labels.empty') }}</p>
            </section>

            <section v-if="selectedRecord.customer_assessment" class="detail-section">
              <h2>{{ t('workOrders.detail.assessment') }}</h2>
              <p>{{ selectedRecord.customer_assessment }}</p>
            </section>

            <section v-if="selectedRecord.handling_requirements" class="detail-section">
              <h2>{{ t('workOrders.detail.requirements') }}</h2>
              <p>{{ selectedRecord.handling_requirements }}</p>
            </section>

            <section v-if="selectedRecord.resident_contact" class="detail-section">
              <h2>{{ t('workOrders.detail.contact') }}</h2>
              <p class="mono">{{ selectedRecord.resident_contact }}</p>
            </section>

            <section class="detail-section">
              <h2>{{ t('workOrders.detail.notification') }}</h2>
              <div class="notification-detail">
                <NTag
                  size="small"
                  :type="notificationTagType(selectedRecord.notification_status)"
                  :bordered="false"
                  :round="false"
                >
                  {{ notificationLabel(selectedRecord.notification_status) }}
                </NTag>
                <span>{{ selectedRecord.assignees.join('、') || t('workOrders.labels.unassigned') }}</span>
              </div>
              <p v-if="selectedRecord.notification_error" class="error-text">
                {{ selectedRecord.notification_error }}
              </p>
            </section>

            <section class="detail-section">
              <h2>{{ t('workOrders.detail.result') }}</h2>
              <p>{{ selectedRecord.result || t('workOrders.labels.noResult') }}</p>
              <span v-if="selectedRecord.responder" class="detail-caption">
                {{ t('workOrders.detail.responder') }}: {{ selectedRecord.responder }}
              </span>
            </section>
          </article>
        </NSpin>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.work-orders-page {
  min-height: 100%;
  background: $bg-primary;
}

.work-orders-header {
  min-height: 74px;
  gap: 20px;

  > div:first-child {
    min-width: 0;
  }
}

.header-meta {
  display: flex;
  gap: 14px;
  margin-top: 3px;
  color: $text-muted;
  font-size: 12px;
}

.export-path {
  min-width: 0;
  max-width: 460px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border-bottom: 1px solid $border-color;
  background: $bg-card;
}

.metric {
  min-width: 0;
  padding: 14px 18px;
  border-right: 1px solid $border-light;

  &:last-child {
    border-right: 0;
  }

  &.alert .metric-value {
    color: $error;
  }
}

.metric-label {
  display: block;
  color: $text-muted;
  font-size: 12px;
  line-height: 1.4;
}

.metric-value {
  display: block;
  margin-top: 2px;
  color: $text-primary;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}

.filter-band {
  display: grid;
  grid-template-columns:
    minmax(220px, 1.4fr)
    repeat(5, minmax(130px, 0.8fr))
    auto;
  gap: 8px;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid $border-color;
}

.search-input {
  min-width: 0;
}

.table-band {
  min-height: 360px;
  background: $bg-card;
  margin-left: 20px;
  margin-top: 10px;
  border-radius: 4px;
}

.ticket-id {
  color: $text-primary;
  font-size: 12px;
}

.issue-cell {
  display: -webkit-box;
  overflow: hidden;
  white-space: normal;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.45;
}

:deep(.clickable-row) {
  cursor: pointer;
}

:deep(.clickable-row:hover td) {
  background: $bg-card-hover !important;
}

.empty-state {
  padding: 80px 20px;
}

.detail-status-row {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid $border-color;
  border-left: 1px solid $border-color;

  > div {
    min-width: 0;
    padding: 12px 14px;
    border-right: 1px solid $border-color;
    border-bottom: 1px solid $border-color;
  }

  dt {
    margin-bottom: 3px;
    color: $text-muted;
    font-size: 12px;
  }

  dd {
    overflow-wrap: anywhere;
    color: $text-primary;
  }
}

.detail-section {
  padding: 18px 0;
  border-bottom: 1px solid $border-color;

  h2 {
    margin-bottom: 7px;
    color: $text-secondary;
    font-size: 13px;
    font-weight: 600;
  }

  p {
    margin: 0;
    color: $text-primary;
    line-height: 1.75;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
}

.notification-detail {
  display: flex;
  align-items: center;
  gap: 10px;
  color: $text-secondary;
}

.error-text {
  margin-top: 9px !important;
  color: $error !important;
  font-size: 12px;
}

.detail-caption {
  display: block;
  margin-top: 8px;
  color: $text-muted;
  font-size: 12px;
}

@media (max-width: 1180px) {
  .metric-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metric:nth-child(3) {
    border-right: 0;
  }

  .metric:nth-child(-n + 3) {
    border-bottom: 1px solid $border-light;
  }

  .filter-band {
    grid-template-columns: repeat(3, minmax(160px, 1fr));
  }
}

@media (max-width: $breakpoint-mobile) {
  .work-orders-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }

  .header-meta {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }

  .header-actions {
    width: 100%;

    :deep(.n-button) {
      flex: 1;
    }
  }

  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metric {
    border-bottom: 1px solid $border-light;
  }

  .metric:nth-child(odd) {
    border-right: 1px solid $border-light;
  }

  .metric:nth-child(2n) {
    border-right: 0;
  }

  .filter-band {
    grid-template-columns: 1fr;
    padding: 12px;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .export-path {
    max-width: 100%;
  }
}
</style>
