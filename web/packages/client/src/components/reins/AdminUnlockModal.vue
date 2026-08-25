<script setup lang="ts">
import {
  computed,
  nextTick,
  ref,
  watch,
} from 'vue'

import {
  NAlert,
  NButton,
  NInput,
  NModal,
} from 'naive-ui'

import {
  useI18n,
} from 'vue-i18n'

import {
  useRouter,
} from 'vue-router'

import {
  useAdminAccessStore,
} from '@/stores/reins/admin-access'

const router =
  useRouter()

const {
  locale,
} = useI18n()

const adminStore =
  useAdminAccessStore()

const password =
  ref('')

const passwordInput =
  ref<any>(null)

const confirmation =
  ref('')

const localError =
  ref('')

const isChinese =
  computed(
    () =>
      locale.value
        .toLowerCase()
        .startsWith('zh'),
  )

const isSetup =
  computed(
    () =>
      !adminStore.configured &&
      adminStore.setupAllowed,
  )

const copy = computed(() =>
  isChinese.value
    ? {
        title: isSetup.value
          ? '设置管理员密码'
          : '管理员访问',
        subtitle: isSetup.value
          ? '仅用于本机开发环境'
          : '此区域仅限管理员使用',
        description: isSetup.value
          ? '首次使用时请设置管理员密码。设置后将立即解锁系统管理功能。'
          : '请输入管理员密码，以访问用户、设置和模型管理。',
        setupNotice: '正式 Windows 安装包会使用构建时配置的管理员密码。',
        notConfigured: '此安装未配置管理员密码，请联系应用发布管理员。',
        passwordLabel: isSetup.value
          ? '新管理员密码'
          : '管理员密码',
        passwordPlaceholder: '请输入密码',
        confirmationLabel: '确认管理员密码',
        confirmationPlaceholder: '请再次输入密码',
        cancel: '取消',
        submit: isSetup.value
          ? '设置并解锁'
          : '解锁',
        mismatch: '两次输入的密码不一致。',
        tooShort: '管理员密码至少需要 12 个字符。',
        required: '请输入管理员密码。',
        invalid: '管理员密码不正确。',
        rateLimited: '尝试次数过多，请稍后再试。',
        setupUnavailable: '管理员密码设置不可用，请联系应用发布管理员。',
        generic: '无法完成管理员验证，请稍后重试。',
      }
    : {
        title: isSetup.value
          ? 'Set administrator password'
          : 'Administrator access',
        subtitle: isSetup.value
          ? 'Local development only'
          : 'This section is restricted',
        description: isSetup.value
          ? 'Set the administrator password for this development installation. The protected system tools will unlock immediately.'
          : 'Enter the administrator password to access Profiles, Settings, and Models.',
        setupNotice: 'Production Windows installers use the administrator password configured during the build.',
        notConfigured: 'This installation has no administrator password. Contact the application release administrator.',
        passwordLabel: isSetup.value
          ? 'New administrator password'
          : 'Administrator password',
        passwordPlaceholder: 'Enter password',
        confirmationLabel: 'Confirm administrator password',
        confirmationPlaceholder: 'Enter password again',
        cancel: 'Cancel',
        submit: isSetup.value
          ? 'Set and unlock'
          : 'Unlock',
        mismatch: 'The passwords do not match.',
        tooShort: 'The administrator password must contain at least 12 characters.',
        required: 'Enter the administrator password.',
        invalid: 'The administrator password is incorrect.',
        rateLimited: 'Too many attempts. Please try again shortly.',
        setupUnavailable: 'Administrator password setup is unavailable. Contact the application release administrator.',
        generic: 'Administrator verification could not be completed. Please try again.',
      },
)

const visibleError = computed(() => {
  if (localError.value) {
    return localError.value
  }

  if (!adminStore.error) {
    return ''
  }

  switch (adminStore.errorCode) {
    case 'password_required':
      return copy.value.required
    case 'invalid_password':
      return copy.value.invalid
    case 'rate_limited':
      return adminStore.retryAfterSeconds > 0
        ? isChinese.value
          ? `尝试次数过多，请在 ${adminStore.retryAfterSeconds} 秒后重试。`
          : `Too many attempts. Try again in ${adminStore.retryAfterSeconds} seconds.`
        : copy.value.rateLimited
    case 'not_configured':
    case 'setup_unavailable':
    case 'already_configured':
      return copy.value.setupUnavailable
    case 'password_too_short':
      return copy.value.tooShort
    default:
      return isChinese.value
        ? copy.value.generic
        : adminStore.error
  }
})

watch(
  () =>
    adminStore.modalOpen,

  async (open) => {
    if (!open) {
      password.value = ''
      confirmation.value = ''
      localError.value = ''
      return
    }

    password.value = ''
    confirmation.value = ''
    localError.value = ''

    await nextTick()

    passwordInput.value
      ?.focus?.()
  },
)

async function submit() {
  if (adminStore.unlocking) {
    return
  }

  localError.value = ''

  if (isSetup.value) {
    if (
      Array.from(password.value)
        .length < 12
    ) {
      localError.value =
        copy.value.tooShort
      return
    }

    if (
      password.value !==
      confirmation.value
    ) {
      localError.value =
        copy.value.mismatch
      return
    }
  }

  const ok = isSetup.value
    ? await adminStore.setup(
        password.value,
      )
    : await adminStore.unlock(
        password.value,
      )

  if (!ok) {
    return
  }

  password.value = ''
  confirmation.value = ''

  const target =
    adminStore.takePendingRoute()

  if (target) {
    await router.push(
      target,
    )
  }
}

function cancel() {
  password.value = ''
  confirmation.value = ''
  localError.value = ''

  adminStore.cancelUnlock()
}
</script>

<template>
  <NModal
    :show="adminStore.modalOpen"
    :mask-closable="false"
    :close-on-esc="true"
    preset="card"
    :bordered="false"
    :style="{
      width: '420px',
      maxWidth: 'calc(100vw - 32px)',
    }"
    @update:show="
      value => {
        if (!value) cancel()
      }
    "
  >
    <template #header>
      <div class="admin-header">
        <div class="admin-icon">
          <svg
            width="21"
            height="21"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <rect
              x="5"
              y="11"
              width="14"
              height="10"
              rx="2"
            />

            <path
              d="M8 11V7a4 4 0 0 1 8 0v4"
            />
          </svg>
        </div>

        <div>
          <div class="admin-title">
            {{ copy.title }}
          </div>

          <div class="admin-subtitle">
            {{ copy.subtitle }}
          </div>
        </div>
      </div>
    </template>

    <div class="admin-content">
      <p>
        {{ copy.description }}
      </p>

      <NAlert
        v-if="!adminStore.configured"
        type="warning"
        :show-icon="true"
      >
        {{
          isSetup
            ? copy.setupNotice
            : copy.notConfigured
        }}
      </NAlert>

      <NAlert
        v-if="visibleError"
        type="error"
        :show-icon="true"
      >
        {{ visibleError }}
      </NAlert>

      <div class="password-field">
        <label>
          {{ copy.passwordLabel }}
        </label>

        <NInput
          ref="passwordInput"
          v-model:value="password"
          type="password"
          show-password-on="click"
          :placeholder="copy.passwordPlaceholder"
          :disabled="adminStore.unlocking"
          @keyup.enter="submit"
        />
      </div>

      <div
        v-if="isSetup"
        class="password-field"
      >
        <label>
          {{ copy.confirmationLabel }}
        </label>

        <NInput
          v-model:value="confirmation"
          type="password"
          show-password-on="click"
          :placeholder="copy.confirmationPlaceholder"
          :disabled="adminStore.unlocking"
          @keyup.enter="submit"
        />
      </div>

      <div class="actions">
        <NButton
          :disabled="adminStore.unlocking"
          @click="cancel"
        >
          {{ copy.cancel }}
        </NButton>

        <NButton
          type="primary"
          :loading="adminStore.unlocking"
          :disabled="
            adminStore.unlocking ||
            !password ||
            (isSetup && !confirmation)
          "
          @click="submit"
        >
          {{ copy.submit }}
        </NButton>
      </div>
    </div>
  </NModal>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.admin-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.admin-icon {
  width: 38px;
  height: 38px;

  display: grid;
  place-items: center;

  flex: 0 0 auto;

  border-radius: 10px;

  color: $text-primary;

  background:
    rgba(
      var(--accent-primary-rgb),
      0.1
    );
}

.admin-title {
  color: $text-primary;
  font-size: 16px;
  font-weight: 700;
}

.admin-subtitle {
  margin-top: 2px;

  color: $text-muted;
  font-size: 12px;
}

.admin-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-content > p {
  margin: 0;

  color: $text-secondary;

  line-height: 1.55;
}

.password-field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.password-field label {
  color: $text-secondary;
  font-size: 12px;
  font-weight: 600;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
