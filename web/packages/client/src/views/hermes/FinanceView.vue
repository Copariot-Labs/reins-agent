<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NButton, NDataTable, useMessage, type DataTableColumns } from 'naive-ui'
import {
  exportFinanceData,
  fetchFinanceSummary,
  fetchFinanceTransactions,
  type FinanceSummary,
  type FinanceTransaction,
  type FinanceTransactionType,
} from '@/api/hermes/finance'
import { downloadFile } from '@/api/hermes/download'

const message = useMessage()
const { t } = useI18n()

const summary = ref<FinanceSummary | null>(null)
const transactions = ref<FinanceTransaction[]>([])
const loading = ref(false)
const exporting = ref(false)
const selectedMonth = ref(currentMonth())
const selectedType = ref<FinanceTransactionType | ''>('')

function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function money(amount: number, currency = 'CNY'): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(amount)
}

function queryParams() {
  return {
    month: selectedMonth.value,
    type: selectedType.value,
    limit: 100,
  }
}

async function loadFinance() {
  loading.value = true
  try {
    const params = queryParams()
    const [summaryResponse, transactionsResponse] = await Promise.all([
      fetchFinanceSummary(params),
      fetchFinanceTransactions(params),
    ])
    summary.value = summaryResponse
    transactions.value = transactionsResponse.transactions
  } catch (err: any) {
    message.error(err?.message || t('finance.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function exportData() {
  exporting.value = true
  try {
    const exported = await exportFinanceData(queryParams())
    await downloadFile(exported.path, exported.fileName)
    message.success(t('finance.exportSuccess', { count: exported.count }))
  } catch (err: any) {
    message.error(err?.message || t('finance.exportFailed'))
  } finally {
    exporting.value = false
  }
}

const typeOptions = computed(() => [
  { label: t('finance.filters.all'), value: '' },
  { label: t('finance.types.income'), value: 'income' },
  { label: t('finance.types.expense'), value: 'expense' },
])

const topCategories = computed(() => {
  const report = summary.value
  if (!report) return []
  const categories = selectedType.value === 'income'
    ? report.income_by_category
    : selectedType.value === 'expense'
      ? report.expense_by_category
      : [...report.expense_by_category, ...report.income_by_category]
  return categories.slice(0, 8)
})

const maxCategoryAmount = computed(() => Math.max(1, ...topCategories.value.map(item => item.amount)))

const columns = computed<DataTableColumns<FinanceTransaction>>(() => [
  {
    title: t('finance.table.date'),
    key: 'occurred_at',
    width: 110,
  },
  {
    title: t('finance.table.type'),
    key: 'type',
    width: 92,
    render: row => h('span', { class: ['type-pill', row.type] }, t(`finance.types.${row.type}`)),
  },
  {
    title: t('finance.table.amount'),
    key: 'amount',
    width: 130,
    align: 'right',
    render: row => h('strong', { class: row.type === 'income' ? 'income-text' : 'expense-text' }, money(row.amount, row.currency)),
  },
  {
    title: t('finance.table.category'),
    key: 'category',
    width: 130,
  },
  {
    title: t('finance.table.description'),
    key: 'description',
    ellipsis: {
      tooltip: true,
    },
  },
  {
    title: t('finance.table.payment'),
    key: 'payment_method',
    width: 110,
    render: row => row.payment_method || '-',
  },
])

onMounted(() => {
  void loadFinance()
})
</script>

<template>
  <div class="finance-view">
    <header class="page-header">
      <h2 class="header-title">{{ t('finance.title') }}</h2>
      <div class="finance-toolbar">
        <input v-model="selectedMonth" class="month-input" type="month" @change="loadFinance" />
        <select v-model="selectedType" class="type-select" @change="loadFinance">
          <option v-for="option in typeOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>        </select>
        <NButton size="small" quaternary :loading="loading" @click="loadFinance">
          {{ t('finance.actions.refresh') }}
        </NButton>
        <NButton size="small" type="primary" :loading="exporting" :disabled="!summary?.databaseExists" @click="exportData">
          {{ t('finance.actions.exportCsv') }}
        </NButton>
      </div>
    </header>

    <main class="finance-content">
      <div v-if="loading && !summary" class="state-block">{{ t('finance.states.loading') }}</div>

      <div v-else-if="summary && !summary.databaseExists" class="state-block">
        {{ t('finance.states.noDatabase') }}
      </div>

      <template v-else-if="summary">
        <section class="stats-grid">
          <div class="stat-card income">
            <span class="stat-label">{{ t('finance.stats.income') }}</span>
            <strong>{{ money(summary.total_income) }}</strong>
          </div>
          <div class="stat-card expense">
            <span class="stat-label">{{ t('finance.stats.expense') }}</span>
            <strong>{{ money(summary.total_expense) }}</strong>
          </div>
          <div class="stat-card net">
            <span class="stat-label">{{ t('finance.stats.net') }}</span>
            <strong>{{ money(summary.net) }}</strong>
          </div>
          <div class="stat-card count">
            <span class="stat-label">{{ t('finance.stats.transactions') }}</span>
            <strong>{{ summary.transaction_count }}</strong>
          </div>
        </section>

        <section class="dashboard-grid">
          <div class="panel">
            <div class="panel-header">
              <h3>{{ t('finance.panels.categories') }}</h3>
              <span>{{ summary.start_date }} - {{ summary.end_date }}</span>
            </div>
            <div v-if="topCategories.length" class="category-list">
              <div v-for="item in topCategories" :key="`${item.category}-${item.amount}`" class="category-row">
                <div class="category-meta">
                  <span>{{ item.category }}</span>
                  <strong>{{ money(item.amount) }}</strong>
                </div>
                <div class="category-track">
                  <div class="category-bar" :style="{ width: `${Math.max(4, item.amount / maxCategoryAmount * 100)}%` }" />
                </div>
              </div>
            </div>
            <div v-else class="empty-panel">{{ t('finance.states.noCategories') }}</div>
          </div>

          <div class="panel">
            <div class="panel-header">
              <h3>{{ t('finance.panels.recent') }}</h3>
              <span>{{ summary.recent_transactions.length }}</span>
            </div>
            <div v-if="summary.recent_transactions.length" class="recent-list">
              <div v-for="tx in summary.recent_transactions" :key="tx.id" class="recent-row">
                <div>
                  <strong>{{ tx.description }}</strong>
                  <span>{{ tx.occurred_at }} · {{ tx.category }}</span>
                </div>
                <em :class="tx.type === 'income' ? 'income-text' : 'expense-text'">
                  {{ money(tx.amount, tx.currency) }}
                </em>
              </div>
            </div>
            <div v-else class="empty-panel">{{ t('finance.states.noRecent') }}</div>
          </div>
        </section>

        <section class="table-section">
          <div class="panel-header table-header">
            <h3>{{ t('finance.panels.transactions') }}</h3>
            <span>{{ transactions.length }}</span>
          </div>
          <NDataTable
            :columns="columns"
            :data="transactions"
            :loading="loading"
            :row-key="row => row.id"
            :pagination="{ pageSize: 12 }"
            size="small"
          />
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.finance-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 21px 20px;
  border-bottom: 1px solid $border-color;
}

.header-title {
  margin: 0;
  color: $text-primary;
  font-size: 16px;
  font-weight: 600;
}

.finance-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.month-input,
.type-select {
  height: 30px;
  border: 1px solid $border-light;
  border-radius: $radius-sm;
  padding: 0 9px;
  color: $text-primary;
  background: $bg-secondary;
  font-size: 13px;
}

.month-input {
  // For Chrome, Edge, Safari
  &::-webkit-calendar-picker-indicator {
    filter: invert(1);
    cursor: pointer;
    color: white;
    
    &:hover {
      opacity: 0.8;
    }
  }
}

.finance-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
}

.stats-grid,
.dashboard-grid {
  display: grid;
  gap: 12px;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 14px;
}

.dashboard-grid {
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.8fr);
  margin-bottom: 14px;
}

.stat-card,
.panel,
.table-section {
  border: 1px solid $border-color;
  border-radius: $radius-sm;
  background: $bg-card;
}

.stat-card {
  padding: 14px;

  strong {
    display: block;
    margin-top: 6px;
    color: $text-primary;
    font-size: 22px;
    font-weight: 700;
    line-height: 1.1;
  }
}

.stat-label {
  color: $text-muted;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
}

.income strong,
.income-text {
  color: $success;
}

.expense strong,
.expense-text {
  color: $error;
}

.net strong {
  color: $accent-primary;
}

.count strong {
  color: $text-primary;
}

.panel,
.table-section {
  padding: 14px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;

  h3 {
    margin: 0;
    color: $text-primary;
    font-size: 14px;
    font-weight: 600;
  }

  span {
    color: $text-muted;
    font-size: 12px;
  }
}

.category-list,
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.category-meta,
.recent-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.category-meta {
  margin-bottom: 5px;

  span,
  strong {
    color: $text-secondary;
    font-size: 13px;
  }
}

.category-track {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: $bg-secondary;
}

.category-bar {
  height: 100%;
  border-radius: inherit;
  background: $accent-primary;
}

.recent-row {
  padding: 8px 0;
  border-bottom: 1px solid $border-light;

  &:last-child {
    border-bottom: 0;
  }

  div {
    min-width: 0;
  }

  strong,
  span {
    display: block;
  }

  strong {
    overflow: hidden;
    color: $text-primary;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  span {
    margin-top: 3px;
    color: $text-muted;
    font-size: 12px;
  }

  em {
    flex-shrink: 0;
    font-style: normal;
    font-weight: 700;
  }
}

.table-header {
  margin-bottom: 10px;
}

.state-block,
.empty-panel {
  padding: 48px 0;
  color: $text-muted;
  text-align: center;
  font-size: 14px;
}

:deep(.type-pill) {
  display: inline-flex;
  align-items: center;
  height: 22px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 12px;
  font-weight: 600;
  text-transform: capitalize;
}

:deep(.type-pill.income) {
  color: $success;
  background: rgba(var(--success-rgb), 0.1);
}

:deep(.type-pill.expense) {
  color: $error;
  background: rgba(var(--error-rgb, 239, 68, 68), 0.1);
}

@media (max-width: $breakpoint-mobile) {
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .finance-toolbar {
    width: 100%;
  }

  .stats-grid,
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .month-input,
  .type-select {
    flex: 1;
    min-width: 132px;
  }
}
</style>
