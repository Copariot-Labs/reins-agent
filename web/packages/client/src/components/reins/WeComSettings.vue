<script setup lang="ts">
import {
  computed,
  onMounted,
  reactive,
  ref,
} from 'vue'

import {
  NAlert,
  NButton,
  NCollapse,
  NCollapseItem,
  NForm,
  NFormItem,
  NInput,
  NSpin,
  NSwitch,
  NTag,
  useMessage,
} from 'naive-ui'

import {
  useI18n,
} from 'vue-i18n'

import {
  fetchWeComSetup,
  saveWeComSetup,
  startWeComService,
  stopWeComService,
  type WeComSetupInput,
  type WeComSetupStatus,
} from '@/api/reins/wecom'

const emit =
  defineEmits<{
    saved: [
      status:
        WeComSetupStatus,
    ]
  }>()

const {
  locale,
} = useI18n()

const message =
  useMessage()

const loading =
  ref(true)

const saving =
  ref(false)

const starting =
  ref(false)

const stopping =
  ref(false)

const refreshing =
  ref(false)

const status =
  ref<
    WeComSetupStatus
    | null
  >(null)

/*
 * IMPORTANT:
 *
 * This switch controls ONLY
 * WeCom group notifications.
 *
 * It does NOT control whether
 * the ticket service is running.
 */
const notificationsEnabled =
  ref(false)

const form =
  reactive<
    WeComSetupInput
  >({
    ticket_api_url: '',
    ticket_api_token: '',

    group_webhook: '',
    reply_bot_name: '',

    users_default: '',
    users_property: '',
    users_cleaning: '',
    users_police: '',
    users_hospital: '',
    users_community: '',
    users_human_review: '',
  })

const isChinese =
  computed(() =>
    locale.value
      .toLowerCase()
      .startsWith('zh'),
  )

const backgroundRunning =
  computed(
    () =>
      status.value
        ?.background
        ?.running === true,
  )

const backgroundInstalled =
  computed(
    () =>
      status.value
        ?.background
        ?.installed === true,
  )

const backgroundState =
  computed(
    () =>
      String(
        status.value
          ?.background
          ?.state ||
        '',
      ).trim(),
  )

const backgroundError =
  computed(
    () =>
      String(
        status.value
          ?.background
          ?.error ||
        '',
      ).trim(),
  )

const copy =
  computed(() =>
    isChinese.value
      ? {
          title:
            '企业微信工单',

          description:
            'Reins 会在后台自动接收和处理工单。后台工单服务和企业微信群通知是两个独立功能。',

          serviceTitle:
            '后台工单服务',

          running:
            '运行中',

          stopped:
            '已停止',

          installed:
            '已安装',

          notInstalled:
            '未安装',

          runningHelp:
            'Reins 正在后台自动接收工单。关闭微信群通知不会停止工单接收。',

          stoppedHelp:
            '后台工单服务当前已停止。已保存的工单接口设置不会丢失。',

          startService:
            '启动服务',

          stopService:
            '停止服务',

          refresh:
            '刷新状态',

          configMissing:
            '请先保存有效的工单接口地址和令牌，然后启动后台服务。',

          ticketUrl:
            '工单接口地址',

          ticketToken:
            '工单接口令牌',

          tokenSaved:
            '令牌已安全保存。留空会继续使用当前令牌；只有需要更换时才输入新值。',

          notificationsTitle:
            '企业微信群通知',

          notificationSwitch:
            '从这台电脑发送企业微信群通知',

          notificationSwitchHelp:
            '只在负责发送群通知的电脑上开启。其他电脑保持关闭，仍然会正常接收和处理工单。',

          fetchOnly:
            '仅接收模式：后台工单服务仍可正常运行、接收和保存工单，但这台电脑不会发送任何企业微信群通知。',

          webhook:
            '企业微信群机器人 Webhook',

          webhookSaved:
            'Webhook 已安全保存。留空会继续使用当前值。',

          recipient:
            '默认接收人 UserID',

          botName:
            '群内机器人名称',

          roleRecipients:
            '角色接收人（可选）',

          property:
            '物业',

          cleaning:
            '保洁',

          police:
            '公安',

          hospital:
            '医院',

          community:
            '社区',

          review:
            '人工审核',

          saveAndStart:
            '保存并启动后台服务',

          saveAndRestart:
            '保存更改并重启服务',

          saved:
            '设置已保存，后台工单服务正在运行。',

          started:
            '后台工单服务已启动。',

          stoppedMessage:
            '后台工单服务已停止。',

          failed:
            '企业微信工单操作失败',
        }
      : {
          title:
            'WeCom work orders',

          description:
            'Reins receives and processes tickets automatically in the background. The ticket service and WeCom group notifications are separate controls.',

          serviceTitle:
            'Background ticket service',

          running:
            'Running',

          stopped:
            'Stopped',

          installed:
            'Installed',

          notInstalled:
            'Not installed',

          runningHelp:
            'Reins is automatically receiving tickets in the background. Turning group notifications off does not stop ticket fetching.',

          stoppedHelp:
            'The background ticket service is currently stopped. Your saved Ticket API settings are kept.',

          startService:
            'Start service',

          stopService:
            'Stop service',

          refresh:
            'Refresh status',

          configMissing:
            'Save a valid Ticket API URL and token before starting the background service.',

          ticketUrl:
            'Ticket API URL',

          ticketToken:
            'Ticket API token',

          tokenSaved:
            'Token is saved securely. Leave this blank to keep the current token; enter a new value only to replace it.',

          notificationsTitle:
            'WeCom group notifications',

          notificationSwitch:
            'Send WeCom group notifications from this computer',

          notificationSwitchHelp:
            'Enable this only on the computer responsible for group notifications. Other computers can keep it off and still receive and process work orders.',

          fetchOnly:
            'Fetch-only mode: the background ticket service can still run, receive and store work orders, but this computer will not send any WeCom group notifications.',

          webhook:
            'WeCom group robot webhook',

          webhookSaved:
            'Webhook is saved securely. Leave this blank to keep the current value.',

          recipient:
            'Default recipient UserID',

          botName:
            'Group bot name',

          roleRecipients:
            'Role recipients (optional)',

          property:
            'Property',

          cleaning:
            'Cleaning',

          police:
            'Police',

          hospital:
            'Hospital',

          community:
            'Community',

          review:
            'Human review',

          saveAndStart:
            'Save and start background service',

          saveAndRestart:
            'Save changes and restart service',

          saved:
            'Settings saved and the background ticket service is running.',

          started:
            'Background ticket service started.',

          stoppedMessage:
            'Background ticket service stopped.',

          failed:
            'WeCom work-order operation failed',
        },
  )

function applyStatus(
  next:
    WeComSetupStatus,
) {
  status.value =
    next

  /*
   * Only literal true enables notifications.
   *
   * false / missing / null = OFF.
   */
  notificationsEnabled.value =
    next.values
      ?.notifications_enabled ===
    true

  Object.assign(
    form,
    {
      ticket_api_url:
        next.values
          ?.ticket_api_url ??
        '',

      reply_bot_name:
        next.values
          ?.reply_bot_name ??
        '',

      users_default:
        next.values
          ?.users_default ??
        '',

      users_property:
        next.values
          ?.users_property ??
        '',

      users_cleaning:
        next.values
          ?.users_cleaning ??
        '',

      users_police:
        next.values
          ?.users_police ??
        '',

      users_hospital:
        next.values
          ?.users_hospital ??
        '',

      users_community:
        next.values
          ?.users_community ??
        '',

      users_human_review:
        next.values
          ?.users_human_review ??
        '',

      /*
       * Secrets are deliberately not returned.
       *
       * Empty fields mean:
       * keep the currently saved secret.
       */
      ticket_api_token:
        '',

      group_webhook:
        '',
    },
  )
}

async function load() {
  loading.value =
    true

  try {
    applyStatus(
      await fetchWeComSetup(),
    )
  } catch (
    error: any
  ) {
    message.error(
      error?.message ||
      copy.value.failed,
    )
  } finally {
    loading.value =
      false
  }
}

/*
 * Refresh service state without overwriting
 * whatever the user is currently typing.
 */
async function refreshStatus() {
  refreshing.value =
    true

  try {
    const next =
      await fetchWeComSetup()

    if (!status.value) {
      applyStatus(next)
      return
    }

    status.value = {
      ...status.value,

      configured:
        next.configured,

      ticket_api_token_configured:
        next.ticket_api_token_configured,

      group_webhook_configured:
        next.group_webhook_configured,

      background:
        next.background,
    }
  } catch (
    error: any
  ) {
    message.error(
      error?.message ||
      copy.value.failed,
    )
  } finally {
    refreshing.value =
      false
  }
}

async function save() {
  saving.value =
    true

  try {
    const payload:
      WeComSetupInput =
      {
        ticket_api_url:
          form.ticket_api_url ??
          '',

        ticket_api_token:
          form.ticket_api_token ??
          '',

        notifications_enabled:
          notificationsEnabled
            .value === true,

        reply_bot_name:
          form.reply_bot_name ??
          '',

        users_default:
          form.users_default ??
          '',

        users_property:
          form.users_property ??
          '',

        users_cleaning:
          form.users_cleaning ??
          '',

        users_police:
          form.users_police ??
          '',

        users_hospital:
          form.users_hospital ??
          '',

        users_community:
          form.users_community ??
          '',

        users_human_review:
          form.users_human_review ??
          '',
      }

    /*
     * A fetch-only computer does not
     * submit a webhook at all.
     */
    if (
      notificationsEnabled.value
    ) {
      payload.group_webhook =
        form.group_webhook ??
        ''
    }

    const next =
      await saveWeComSetup(
        payload,
      )

    applyStatus(next)

    message.success(
      copy.value.saved,
    )

    emit(
      'saved',
      next,
    )
  } catch (
    error: any
  ) {
    message.error(
      error?.message ||
      copy.value.failed,
    )
  } finally {
    saving.value =
      false
  }
}

async function startService() {
  starting.value =
    true

  try {
    const next =
      await startWeComService()

    applyStatus(next)

    message.success(
      copy.value.started,
    )

    emit(
      'saved',
      next,
    )
  } catch (
    error: any
  ) {
    message.error(
      error?.message ||
      copy.value.failed,
    )
  } finally {
    starting.value =
      false
  }
}

async function stopService() {
  stopping.value =
    true

  try {
    const next =
      await stopWeComService()

    applyStatus(next)

    message.success(
      copy.value.stoppedMessage,
    )

    emit(
      'saved',
      next,
    )
  } catch (
    error: any
  ) {
    message.error(
      error?.message ||
      copy.value.failed,
    )
  } finally {
    stopping.value =
      false
  }
}

onMounted(load)
</script>

<template>
  <section class="wecom-settings">
    <header>
      <h3>
        {{ copy.title }}
      </h3>

      <p>
        {{ copy.description }}
      </p>
    </header>

    <NSpin :show="loading">
      <!-- Background service -->
      <div class="service-card">
        <div class="service-card__content">
          <div class="service-card__title">
            <strong>
              {{ copy.serviceTitle }}
            </strong>

            <NTag
              :type="
                backgroundRunning
                  ? 'success'
                  : 'warning'
              "
              size="small"
              round
            >
              {{
                backgroundRunning
                  ? copy.running
                  : copy.stopped
              }}
            </NTag>

            <NTag
              v-if="
                !backgroundRunning
              "
              size="small"
              round
            >
              {{
                backgroundInstalled
                  ? copy.installed
                  : copy.notInstalled
              }}
            </NTag>
          </div>

          <p>
            {{
              backgroundRunning
                ? copy.runningHelp
                : copy.stoppedHelp
            }}
          </p>

          <p
            v-if="backgroundState"
            class="service-state"
          >
            State:
            {{ backgroundState }}
          </p>
        </div>

        <div class="service-card__actions">
          <NButton
            secondary
            :loading="refreshing"
            :disabled="
              saving ||
              starting ||
              stopping
            "
            @click="refreshStatus"
          >
            {{ copy.refresh }}
          </NButton>

          <NButton
            v-if="backgroundRunning"
            secondary
            type="error"
            :loading="stopping"
            :disabled="
              saving ||
              starting
            "
            @click="stopService"
          >
            {{ copy.stopService }}
          </NButton>

          <NButton
            v-else
            secondary
            type="primary"
            :loading="starting"
            :disabled="
              !status?.configured ||
              saving ||
              stopping
            "
            @click="startService"
          >
            {{ copy.startService }}
          </NButton>
        </div>
      </div>

      <NAlert
        v-if="backgroundError"
        type="warning"
        :show-icon="true"
        class="service-alert"
      >
        {{ backgroundError }}
      </NAlert>

      <NAlert
        v-if="
          status &&
          !status.configured
        "
        type="info"
        :show-icon="true"
        class="service-alert"
      >
        {{ copy.configMissing }}
      </NAlert>

      <NForm
        label-placement="top"
        class="setup-form"
      >
        <!-- Ticket API -->
        <NFormItem
          :label="copy.ticketUrl"
        >
          <NInput
            v-model:value="
              form.ticket_api_url
            "
            placeholder="https://example.com/internal/tickets"
          />
        </NFormItem>

        <NFormItem
          :label="copy.ticketToken"
        >
          <NInput
            v-model:value="
              form.ticket_api_token
            "
            type="password"
            show-password-on="click"
            :placeholder="
              status
                ?.ticket_api_token_configured
                ? 'Saved securely ••••••••••••'
                : copy.ticketToken
            "
          />

          <p
            v-if="
              status
                ?.ticket_api_token_configured
            "
            class="field-help"
          >
            {{ copy.tokenSaved }}
          </p>
        </NFormItem>

        <!-- Notifications -->
        <div class="section-heading">
          {{ copy.notificationsTitle }}
        </div>

        <div class="notification-setting">
          <div class="notification-setting__content">
            <strong>
              {{ copy.notificationSwitch }}
            </strong>

            <p>
              {{ copy.notificationSwitchHelp }}
            </p>
          </div>

          <NSwitch
            v-model:value="
              notificationsEnabled
            "
          />
        </div>

        <NAlert
          v-if="
            !notificationsEnabled
          "
          type="info"
          :show-icon="true"
          class="fetch-only-alert"
        >
          {{ copy.fetchOnly }}
        </NAlert>

        <!-- Notification-only configuration -->
        <template
          v-if="
            notificationsEnabled
          "
        >
          <NFormItem
            :label="copy.webhook"
          >
            <NInput
              v-model:value="
                form.group_webhook
              "
              type="password"
              show-password-on="click"
              :placeholder="
                status
                  ?.group_webhook_configured
                  ? 'Saved securely ••••••••••••'
                  : 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...'
              "
            />

            <p
              v-if="
                status
                  ?.group_webhook_configured
              "
              class="field-help"
            >
              {{ copy.webhookSaved }}
            </p>
          </NFormItem>

          <div class="form-grid">
            <NFormItem
              :label="copy.recipient"
            >
              <NInput
                v-model:value="
                  form.users_default
                "
                placeholder="user_id"
              />
            </NFormItem>

            <NFormItem
              :label="copy.botName"
            >
              <NInput
                v-model:value="
                  form.reply_bot_name
                "
              />
            </NFormItem>
          </div>

          <NCollapse>
            <NCollapseItem
              name="roles"
              :title="
                copy.roleRecipients
              "
            >
              <div class="form-grid">
                <NFormItem
                  :label="
                    copy.property
                  "
                >
                  <NInput
                    v-model:value="
                      form.users_property
                    "
                  />
                </NFormItem>

                <NFormItem
                  :label="
                    copy.cleaning
                  "
                >
                  <NInput
                    v-model:value="
                      form.users_cleaning
                    "
                  />
                </NFormItem>

                <NFormItem
                  :label="
                    copy.police
                  "
                >
                  <NInput
                    v-model:value="
                      form.users_police
                    "
                  />
                </NFormItem>

                <NFormItem
                  :label="
                    copy.hospital
                  "
                >
                  <NInput
                    v-model:value="
                      form.users_hospital
                    "
                  />
                </NFormItem>

                <NFormItem
                  :label="
                    copy.community
                  "
                >
                  <NInput
                    v-model:value="
                      form.users_community
                    "
                  />
                </NFormItem>

                <NFormItem
                  :label="
                    copy.review
                  "
                >
                  <NInput
                    v-model:value="
                      form.users_human_review
                    "
                  />
                </NFormItem>
              </div>
            </NCollapseItem>
          </NCollapse>
        </template>

        <div class="actions">
          <NButton
            type="primary"
            :loading="saving"
            :disabled="
              starting ||
              stopping
            "
            @click="save"
          >
            {{
              backgroundRunning
                ? copy.saveAndRestart
                : copy.saveAndStart
            }}
          </NButton>
        </div>
      </NForm>
    </NSpin>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.wecom-settings {
  max-width: 900px;
  padding: 8px 0 24px;
}

header h3 {
  margin: 0 0 6px;
  font-size: 18px;
}

header p {
  margin: 0 0 18px;
  color: $text-muted;
  line-height: 1.55;
}

.service-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;

  padding: 16px 18px;

  border: 1px solid $border-color;
  border-radius: 10px;
}

.service-card__content {
  min-width: 0;
}

.service-card__title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.service-card__content p {
  margin: 6px 0 0;
  color: $text-muted;
  line-height: 1.5;
}

.service-card__actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

.service-state {
  font-size: 12px;
}

.service-alert {
  margin-top: 12px;
}

.setup-form {
  margin-top: 22px;
}

.section-heading {
  margin: 10px 0;
  font-size: 15px;
  font-weight: 600;
}

.notification-setting {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;

  margin-bottom: 16px;
  padding: 16px;

  border: 1px solid $border-color;
  border-radius: 10px;
}

.notification-setting__content {
  min-width: 0;
}

.notification-setting__content strong {
  display: block;
  margin-bottom: 4px;
}

.notification-setting__content p {
  margin: 0;
  color: $text-muted;
  line-height: 1.5;
}

.field-help {
  margin: 7px 0 0;
  color: $text-muted;
  font-size: 12px;
  line-height: 1.5;
}

.fetch-only-alert {
  margin-bottom: 18px;
}

.form-grid {
  display: grid;
  grid-template-columns:
    repeat(
      2,
      minmax(0, 1fr)
    );
  gap: 0 16px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

@media (max-width: 760px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .service-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .service-card__actions {
    width: 100%;
  }

  .notification-setting {
    align-items: flex-start;
  }
}
</style>
