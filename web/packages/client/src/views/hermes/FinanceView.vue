<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { NAutoComplete, NButton, NDataTable, NForm, NFormItem, NInput, NInputNumber, NModal, NPopconfirm, NSelect, useMessage, type DataTableColumns } from 'naive-ui'
import {
  createFinanceTransaction,
  deleteFinanceTransaction as deleteFinanceTransactionApi,
  exportFinanceData,
  fetchFinanceSummary,
  fetchFinanceTransactions,
  updateFinanceTransaction,
  type FinanceTransactionInput,
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
const savingTransaction = ref(false)
const deletingTransactionId = ref<number | null>(null)
const editorVisible = ref(false)
const editingTransaction = ref<FinanceTransaction | null>(null)
const selectedMonth = ref(currentMonth())
const selectedType = ref<FinanceTransactionType | ''>('')
const form = ref<FinanceFormState>(newFinanceForm())

const expenseCategoryRecommendations = [
  '餐饮',
  '交通',
  '办公',
  '住房',
  '水电',
  '购物',
  '医疗',
  '娱乐',
  '其他支出',
]

const incomeCategoryRecommendations = [
  '工资',
  '业务收入',
  '项目款',
  '奖金',
  '退款',
  '投资收益',
  '其他收入',
]

const paymentMethodRecommendations = [
  '微信',
  '支付宝',
  '银行卡',
  '信用卡',
  '现金',
  'Apple Pay',
]

interface FinanceFormState {
  type: FinanceTransactionType
  amount: number | null
  currency: string
  category: string
  description: string
  counterparty: string
  payment_method: string
  occurred_at: string
}

function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function currentDate(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function defaultCategory(type: FinanceTransactionType): string {
  return type === 'income' ? '其他收入' : '其他支出'
}

function newFinanceForm(transaction?: FinanceTransaction | null): FinanceFormState {
  if (transaction) {
    return {
      type: transaction.type,
      amount: transaction.amount,
      currency: transaction.currency || 'CNY',
      category: transaction.category || defaultCategory(transaction.type),
      description: transaction.description || '',
      counterparty: transaction.counterparty || '',
      payment_method: transaction.payment_method || '',
      occurred_at: transaction.occurred_at || currentDate(),
    }
  }

  const type = selectedType.value || 'expense'
  return {
    type,
    amount: null,
    currency: 'CNY',
    category: defaultCategory(type),
    description: '',
    counterparty: '',
    payment_method: '',
    occurred_at: currentDate(),
  }
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

function openCreateEditor() {
  editingTransaction.value = null
  form.value = newFinanceForm()
  editorVisible.value = true
}

function openEditEditor(transaction: FinanceTransaction) {
  editingTransaction.value = transaction
  form.value = newFinanceForm(transaction)
  editorVisible.value = true
}

function closeEditor() {
  if (savingTransaction.value) return
  editorVisible.value = false
}

function handleFormTypeUpdate(value: FinanceTransactionType) {
  const previousDefault = defaultCategory(form.value.type)
  if (!form.value.category.trim() || form.value.category === previousDefault) {
    form.value.category = defaultCategory(value)
  }
  form.value.type = value
}

function unique(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))]
}

function buildSuggestionOptions(values: Array<string | null | undefined>, input: string) {
  const keyword = input.trim().toLowerCase()
  const filtered = unique(values).filter(value => !keyword || value.toLowerCase().includes(keyword))
  const options = filtered.slice(0, 8)

  if (keyword && !options.some(value => value.toLowerCase() === keyword)) {
    options.unshift(input.trim())
  }

  return options.map(value => ({ label: value, value }))
}

function buildTransactionInput(): FinanceTransactionInput | null {
  const value = form.value
  const amount = Number(value.amount)

  if (!Number.isFinite(amount) || amount <= 0) {
    message.error(t('finance.form.amountRequired'))
    return null
  }

  if (!value.occurred_at) {
    message.error(t('finance.form.dateRequired'))
    return null
  }

  if (!value.category.trim()) {
    message.error(t('finance.form.categoryRequired'))
    return null
  }

  if (!value.description.trim()) {
    message.error(t('finance.form.descriptionRequired'))
    return null
  }

  return {
    type: value.type,
    amount,
    currency: value.currency.trim() || 'CNY',
    category: value.category.trim(),
    description: value.description.trim(),
    counterparty: value.counterparty.trim() || null,
    payment_method: value.payment_method.trim() || null,
    occurred_at: value.occurred_at,
  }
}

async function saveTransaction() {
  const payload = buildTransactionInput()
  if (!payload) return

  savingTransaction.value = true
  try {
    if (editingTransaction.value) {
      await updateFinanceTransaction(editingTransaction.value.id, payload)
      message.success(t('finance.updateSuccess'))
    } else {
      await createFinanceTransaction(payload)
      message.success(t('finance.createSuccess'))
    }

    selectedMonth.value = payload.occurred_at.slice(0, 7)
    if (selectedType.value && selectedType.value !== payload.type) selectedType.value = ''
    editorVisible.value = false
    await loadFinance()
  } catch (err: any) {
    message.error(err?.message || t('finance.saveFailed'))
  } finally {
    savingTransaction.value = false
  }
}

async function deleteTransaction(transaction: FinanceTransaction) {
  if (deletingTransactionId.value !== null) return

  deletingTransactionId.value = transaction.id
  try {
    await deleteFinanceTransactionApi(transaction.id)
    message.success(t('finance.deleteSuccess'))
    if (editingTransaction.value?.id === transaction.id) {
      editorVisible.value = false
      editingTransaction.value = null
    }
    await loadFinance()
  } catch (err: any) {
    message.error(err?.message || t('finance.deleteFailed'))
  } finally {
    deletingTransactionId.value = null
  }
}

const typeOptions = computed(() => [
  { label: t('finance.filters.all'), value: '' },
  { label: t('finance.types.income'), value: 'income' },
  { label: t('finance.types.expense'), value: 'expense' },
])

const transactionTypeOptions = computed(() => [
  { label: t('finance.types.expense'), value: 'expense' },
  { label: t('finance.types.income'), value: 'income' },
])

const categoryOptions = computed(() => {
  const summaryCategories = form.value.type === 'income'
    ? summary.value?.income_by_category.map(item => item.category) || []
    : summary.value?.expense_by_category.map(item => item.category) || []
  const tableCategories = transactions.value
    .filter(transaction => transaction.type === form.value.type)
    .map(transaction => transaction.category)
  const defaults = form.value.type === 'income'
    ? incomeCategoryRecommendations
    : expenseCategoryRecommendations

  return buildSuggestionOptions([
    ...summaryCategories,
    ...tableCategories,
    ...defaults,
  ], form.value.category)
})

const paymentMethodOptions = computed(() => buildSuggestionOptions([
  ...transactions.value.map(transaction => transaction.payment_method),
  ...paymentMethodRecommendations,
], form.value.payment_method))

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
  {
    title: t('finance.table.actions'),
    key: 'actions',
    width: 150,
    align: 'right',
    // render: (row) => {
    //   const isDeleting = deletingTransactionId.value === row.id

    //   return h('div', { class: 'table-actions' }, [
    //     h(NButton, {
    //       size: 'tiny',
    //       quaternary: true,
    //       disabled: isDeleting,
    //       onClick: () => openEditEditor(row),
    //     }, { default: () => h('svg', {
    //     xmlns: "http://www.w3.org/2000/svg",
    //     width: "14",
    //     height: "14",
    //     viewBox: "0 0 24 24",
    //     fill: "none",
    //     stroke: "currentColor",
    //     "stroke-width": "2",
    //     "stroke-linecap": "round",
    //     "stroke-linejoin": "round"
    //   }, [
    //     h('path', { d: "M17 3l4 4-7 7H10v-4l7-7z" }),
    //     h('path', { d: "M4 20h16" })
    //   ]) }),
    //     h(NPopconfirm, {
    //       negativeText: t('common.cancel'),
    //       positiveText: t('common.confirm'),
    //       negativeButtonProps: {
    //         disabled: isDeleting,
    //       },
    //       positiveButtonProps: {
    //         loading: isDeleting,
    //         disabled: isDeleting,
    //       },
    //       onPositiveClick: () => deleteTransaction(row),
    //     }, {
    //       default: () => t('finance.deleteConfirm'),
    //       trigger: () => h(NButton, {
    //         size: 'tiny',
    //         quaternary: true,
    //         type: 'error',
    //         loading: isDeleting,
    //         disabled: deletingTransactionId.value !== null && !isDeleting,
    //       }, { default: () => t('finance.actions.delete') }),
    //     }),
    //   ])
    // },
    render: (row) => {
  const isDeleting = deletingTransactionId.value === row.id

  return h('div', { class: 'table-actions' }, [
        // Edit button with icon
        h(NButton, {
          size: 'tiny',
          quaternary: true,
          disabled: isDeleting,
          onClick: () => openEditEditor(row),
        }, { 
          default: () => h('svg', {
            xmlns: "http://www.w3.org/2000/svg",
            width: "14",
            height: "14",
            viewBox: "0 0 24 24",
            fill: "none",
            stroke: "currentColor",
            "stroke-width": "2",
            "stroke-linecap": "round",
            "stroke-linejoin": "round"
          }, [
            h('path', { d: "M17 3l4 4-7 7H10v-4l7-7z" }),
            h('path', { d: "M4 20h16" })
          ])
        }),
        
        // Delete button with icon and confirmation
        h(NPopconfirm, {
          negativeText: t('common.cancel'),
          positiveText: t('common.confirm'),
          negativeButtonProps: {
            disabled: isDeleting,
          },
          positiveButtonProps: {
            loading: isDeleting,
            disabled: isDeleting,
          },
          onPositiveClick: () => deleteTransaction(row),
        }, {
          default: () => t('finance.deleteConfirm'),
          trigger: () => h(NButton, {
            size: 'tiny',
            quaternary: true,
            type: 'error',
            loading: isDeleting,
            disabled: deletingTransactionId.value !== null && !isDeleting,
          }, { 
            default: () => h('svg', {
              xmlns: "http://www.w3.org/2000/svg",
              width: "14",
              height: "14",
              viewBox: "0 0 24 24",
              fill: "none",
              stroke: "currentColor",
              "stroke-width": "2",
              "stroke-linecap": "round",
              "stroke-linejoin": "round"
            }, [
              h('path', { d: "M3 6h18" }),
              h('path', { d: "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" }),
              h('line', { x1: "10", y1: "11", x2: "10", y2: "17" }),
              h('line', { x1: "14", y1: "11", x2: "14", y2: "17" })
            ])
          }),
        }),
      ])
    }
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
          </option>
        </select>
        <NButton size="small" type="primary" @click="openCreateEditor">
          {{ t('finance.actions.addTransaction') }}
        </NButton>
        <NButton size="small" quaternary :loading="loading" @click="loadFinance">
          {{ t('finance.actions.refresh') }}
        </NButton>
        <NButton size="small" secondary :loading="exporting" :disabled="!summary?.databaseExists" @click="exportData">
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
            class="transaction-table"
            :columns="columns"
            :data="transactions"
            :loading="loading"
            :row-key="row => row.id"
            :pagination="{ pageSize: 12 }"
            :scroll-x="860"
            size="small"
          />
        </section>
      </template>
    </main>

    <NModal
      v-model:show="editorVisible"
      preset="card"
      class="finance-editor-modal"
      :mask-closable="!savingTransaction"
      :title="editingTransaction ? t('finance.form.editTitle') : t('finance.form.addTitle')"
    >
      <NForm class="finance-form" label-placement="top">
        <div class="form-grid">
          <NFormItem :label="t('finance.form.type')">
            <NSelect
              :value="form.type"
              :options="transactionTypeOptions"
              @update:value="handleFormTypeUpdate"
            />
          </NFormItem>
          <NFormItem :label="t('finance.form.amount')">
            <NInputNumber
              v-model:value="form.amount"
              :min="0.01"
              :precision="2"
              :show-button="false"
              class="full-input"
            />
          </NFormItem>
          <NFormItem :label="t('finance.form.currency')">
            <NInput v-model:value="form.currency" maxlength="8" />
          </NFormItem>
          <NFormItem :label="t('finance.form.date')">
            <input v-model="form.occurred_at" class="form-control" type="date" />
          </NFormItem>
        </div>

        <div class="form-grid">
          <NFormItem :label="t('finance.form.category')">
            <NAutoComplete
              v-model:value="form.category"
              :options="categoryOptions"
              :placeholder="t('finance.form.categoryPlaceholder')"
              clearable
            />
          </NFormItem>
          <NFormItem :label="t('finance.form.paymentMethod')">
            <NAutoComplete
              v-model:value="form.payment_method"
              :options="paymentMethodOptions"
              :placeholder="t('finance.form.paymentMethodPlaceholder')"
              clearable
            />
          </NFormItem>
        </div>

        <NFormItem :label="t('finance.form.description')">
          <NInput
            v-model:value="form.description"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
          />
        </NFormItem>

        <NFormItem :label="t('finance.form.counterparty')">
          <NInput v-model:value="form.counterparty" />
        </NFormItem>
      </NForm>

      <div class="modal-actions">
        <NButton :disabled="savingTransaction" @click="closeEditor">
          {{ t('common.cancel') }}
        </NButton>
        <NButton type="primary" :loading="savingTransaction" @click="saveTransaction">
          {{ t('common.save') }}
        </NButton>
      </div>
    </NModal>
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

.transaction-table {
  width: 100%;
}

.transaction-table :deep(.n-data-table-wrapper) {
  -webkit-overflow-scrolling: touch;
}

.transaction-table :deep(.n-data-table__pagination) {
  justify-content: flex-end;
  margin: 12px 0 0;
  overflow-x: auto;
  max-width: 100%;
  -webkit-overflow-scrolling: touch;
}

:deep(.table-actions) {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  width: 100%;
}

.state-block,
.empty-panel {
  padding: 48px 0;
  color: $text-muted;
  text-align: center;
  font-size: 14px;
}

:global(.finance-editor-modal) {
  width: min(680px, calc(100vw - 32px));
}

.finance-form {
  margin-top: 4px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 12px;
}

.full-input {
  width: 100%;
}

.form-control {
  width: 100%;
  height: 34px;
  border: 1px solid $border-light;
  border-radius: $radius-sm;
  padding: 0 10px;
  color: $text-primary;
  background: $bg-secondary;
  font-size: 14px;
  outline: none;
  // For Chrome, Edge, Safari
  &::-webkit-calendar-picker-indicator {
    filter: invert(1);
    cursor: pointer;
    color: white;
  }

  &:focus {
    border-color: $accent-primary;
  }
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
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

  .form-grid {
    grid-template-columns: 1fr;
  }

  .transaction-table :deep(.n-data-table__pagination) {
    justify-content: center;
  }

  .transaction-table :deep(.n-pagination) {
    flex-wrap: wrap;
    justify-content: center;
    row-gap: 6px;
  }
}
</style>
