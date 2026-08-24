<script setup lang="ts">
import {
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
  useRouter,
} from 'vue-router'

import {
  useAdminAccessStore,
} from '@/stores/reins/admin-access'

const router =
  useRouter()

const adminStore =
  useAdminAccessStore()

const password =
  ref('')

const passwordInput =
  ref<any>(null)

watch(
  () =>
    adminStore.modalOpen,

  async (open) => {
    if (!open) {
      password.value = ''
      return
    }

    password.value = ''

    await nextTick()

    passwordInput.value
      ?.focus?.()
  },
)

async function submit() {
  const ok =
    await adminStore.unlock(
      password.value,
    )

  if (!ok) {
    return
  }

  password.value = ''

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
            Administrator access
          </div>

          <div class="admin-subtitle">
            This section is restricted.
          </div>
        </div>
      </div>
    </template>

    <div class="admin-content">
      <p>
        Enter the administrator password to access
        Profile, Settings, and Models.
      </p>

      <NAlert
        v-if="!adminStore.configured"
        type="warning"
        :show-icon="true"
      >
        Administrator access is not configured on this
        Reins installation.
      </NAlert>

      <NAlert
        v-if="adminStore.error"
        type="error"
        :show-icon="true"
      >
        {{ adminStore.error }}
      </NAlert>

      <div class="password-field">
        <label>
          Administrator password
        </label>

        <NInput
          ref="passwordInput"
          v-model:value="password"
          type="password"
          show-password-on="click"
          placeholder="Enter password"
          :disabled="adminStore.unlocking"
          @keyup.enter="submit"
        />
      </div>

      <div class="actions">
        <NButton
          :disabled="adminStore.unlocking"
          @click="cancel"
        >
          Cancel
        </NButton>

        <NButton
          type="primary"
          :loading="adminStore.unlocking"
          :disabled="
            !password ||
            !adminStore.configured
          "
          @click="submit"
        >
          Unlock
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