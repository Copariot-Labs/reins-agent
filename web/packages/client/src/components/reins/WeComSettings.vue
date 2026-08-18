<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCollapse,
  NCollapseItem,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpin,
  useMessage,
} from 'naive-ui'
import { useI18n } from 'vue-i18n'
import {
  fetchWeComSetup,
  saveWeComSetup,
  type WeComSetupInput,
  type WeComSetupStatus,
} from '@/api/reins/wecom'

const emit = defineEmits<{ saved: [status: WeComSetupStatus] }>()
const { locale } = useI18n()
const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const status = ref<WeComSetupStatus | null>(null)
const form = reactive<WeComSetupInput>({})
const isChinese = computed(() => locale.value.toLowerCase().startsWith('zh'))
const copy = computed(() => isChinese.value ? {
  title: '企业微信工单',
  description: '连接工单接口和企业微信群机器人。保存后，Reins 会自动在后台接收并分派工单。',
  configured: '企业微信后台服务正在运行。',
  pending: '完成以下设置后，Reins 才能在后台接收工单。',
  ticketUrl: '工单接口地址',
  ticketToken: '工单接口令牌',
  webhook: '企业微信群机器人 Webhook',
  recipient: '默认接收人 UserID',
  botName: '群内机器人名称',
  pollInterval: '检查间隔（秒）',
  routing: '分派方式',
  advanced: '角色接收人（可选）',
  property: '物业',
  cleaning: '保洁',
  police: '公安',
  hospital: '医院',
  community: '社区',
  review: '人工审核',
  secretSaved: '已保存。留空可继续使用当前值',
  save: '保存并启动后台服务',
  saved: '企业微信已连接，后台工单服务已启动。',
  failed: '无法保存企业微信设置',
} : {
  title: 'WeCom work orders',
  description: 'Connect the ticket API and WeCom group robot. Reins will receive and route tickets automatically in the background.',
  configured: 'The WeCom background service is running.',
  pending: 'Complete this setup before Reins can receive tickets in the background.',
  ticketUrl: 'Ticket API URL',
  ticketToken: 'Ticket API token',
  webhook: 'WeCom group robot webhook',
  recipient: 'Default recipient UserID',
  botName: 'Group bot name',
  pollInterval: 'Check interval (seconds)',
  routing: 'Routing mode',
  advanced: 'Role recipients (optional)',
  property: 'Property',
  cleaning: 'Cleaning',
  police: 'Police',
  hospital: 'Hospital',
  community: 'Community',
  review: 'Human review',
  secretSaved: 'Already saved. Leave blank to keep the current value',
  save: 'Save and start background service',
  saved: 'WeCom is connected and its background service has started.',
  failed: 'Could not save WeCom settings',
})

const routingOptions = [
  { label: 'Hybrid', value: 'hybrid' },
  { label: 'Rules', value: 'rules' },
  { label: 'Shadow', value: 'shadow' },
]

function applyStatus(next: WeComSetupStatus) {
  status.value = next
  Object.assign(form, next.values, {
    ticket_api_token: '',
    group_webhook: '',
  })
}

async function load() {
  loading.value = true
  try {
    applyStatus(await fetchWeComSetup())
  } catch (error: any) {
    message.error(error?.message || copy.value.failed)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const next = await saveWeComSetup(form)
    applyStatus(next)
    message.success(copy.value.saved)
    emit('saved', next)
  } catch (error: any) {
    message.error(error?.message || copy.value.failed)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="wecom-settings">
    <header>
      <h3>{{ copy.title }}</h3>
      <p>{{ copy.description }}</p>
    </header>
    <NSpin :show="loading">
      <NAlert :type="status?.configured ? 'success' : 'warning'" :show-icon="true">
        {{ status?.configured ? copy.configured : copy.pending }}
      </NAlert>

      <NForm label-placement="top" class="setup-form">
        <div class="form-grid">
          <NFormItem :label="copy.ticketUrl">
            <NInput v-model:value="form.ticket_api_url" placeholder="https://example.com/internal/tickets" />
          </NFormItem>
          <NFormItem :label="copy.pollInterval">
            <NInput v-model:value="form.poll_interval" inputmode="numeric" placeholder="30" />
          </NFormItem>
        </div>
        <NFormItem :label="copy.ticketToken">
          <NInput
            v-model:value="form.ticket_api_token"
            type="password"
            show-password-on="click"
            :placeholder="status?.ticket_api_token_configured ? copy.secretSaved : copy.ticketToken"
          />
        </NFormItem>
        <NFormItem :label="copy.webhook">
          <NInput
            v-model:value="form.group_webhook"
            type="password"
            show-password-on="click"
            :placeholder="status?.group_webhook_configured ? copy.secretSaved : 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...'"
          />
        </NFormItem>
        <div class="form-grid">
          <NFormItem :label="copy.recipient">
            <NInput v-model:value="form.users_default" placeholder="user_id" />
          </NFormItem>
          <NFormItem :label="copy.botName">
            <NInput v-model:value="form.reply_bot_name" />
          </NFormItem>
          <NFormItem :label="copy.routing">
            <NSelect v-model:value="form.routing_mode" :options="routingOptions" />
          </NFormItem>
        </div>

        <NCollapse>
          <NCollapseItem name="roles" :title="copy.advanced">
            <div class="form-grid">
              <NFormItem :label="copy.property"><NInput v-model:value="form.users_property" /></NFormItem>
              <NFormItem :label="copy.cleaning"><NInput v-model:value="form.users_cleaning" /></NFormItem>
              <NFormItem :label="copy.police"><NInput v-model:value="form.users_police" /></NFormItem>
              <NFormItem :label="copy.hospital"><NInput v-model:value="form.users_hospital" /></NFormItem>
              <NFormItem :label="copy.community"><NInput v-model:value="form.users_community" /></NFormItem>
              <NFormItem :label="copy.review"><NInput v-model:value="form.users_human_review" /></NFormItem>
            </div>
          </NCollapseItem>
        </NCollapse>

        <div class="actions">
          <NButton type="primary" :loading="saving" @click="save">{{ copy.save }}</NButton>
        </div>
      </NForm>
    </NSpin>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.wecom-settings { max-width: 840px; padding: 8px 0 24px; }
header h3 { margin: 0 0 6px; font-size: 18px; }
header p { margin: 0 0 18px; color: $text-muted; line-height: 1.55; }
.setup-form { margin-top: 18px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.actions { display: flex; justify-content: flex-end; margin-top: 20px; }
@media (max-width: 760px) { .form-grid { grid-template-columns: 1fr; } }
</style>
