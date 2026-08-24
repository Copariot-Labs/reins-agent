<script setup lang="ts">
import {
  computed,
  onMounted,
  onUnmounted,
  ref,
  watch,
} from 'vue'

import {
  useRoute,
  useRouter,
} from 'vue-router'

import {
  darkTheme,
  NConfigProvider,
  NDialogProvider,
  NMessageProvider,
  NNotificationProvider,
} from 'naive-ui'

import {
  useI18n,
} from 'vue-i18n'

import {
  getThemeOverrides,
} from '@/styles/theme'

import {
  useTheme,
} from '@/composables/useTheme'

import AppSidebar
  from '@/components/layout/AppSidebar.vue'

import SessionSearchModal
  from '@/components/hermes/chat/SessionSearchModal.vue'

import AuthEventListener
  from '@/components/auth/AuthEventListener.vue'

import DefaultCredentialPrompt
  from '@/components/auth/DefaultCredentialPrompt.vue'

import WeComSetupPrompt
  from '@/components/reins/WeComSetupPrompt.vue'

import AdminUnlockModal
  from '@/components/reins/AdminUnlockModal.vue'

import {
  useKeyboard,
} from '@/composables/useKeyboard'

import {
  useAppStore,
} from '@/stores/hermes/app'

import {
  useAdminAccessStore,
} from '@/stores/reins/admin-access'

import {
  isTauriDesktop,
} from '@/api/client'

const {
  isDark,
  isComic,
} = useTheme()

const {
  t,
} = useI18n()

const appStore =
  useAppStore()

const adminStore =
  useAdminAccessStore()

const route =
  useRoute()

const router =
  useRouter()

const ready =
  ref(false)

const themeOverrides =
  computed(
    () =>
      getThemeOverrides(
        isDark.value,
        isComic.value,
      ),
  )

const naiveTheme =
  computed(
    () =>
      isDark.value
        ? darkTheme
        : null,
  )

const isLoginPage =
  computed(
    () =>
      !isTauriDesktop() &&
      route.name ===
        'login',
  )

const nodeVersionLow =
  computed(() => {
    const version =
      appStore.nodeVersion

    const major =
      parseInt(
        version.split(
          '.',
        )[0],
        10,
      )

    return (
      !Number.isNaN(
        major,
      ) &&
      major < 23
    )
  })

watch(
  () => route.path,

  () => {
    appStore.closeSidebar()
  },
)

router
  .isReady()
  .then(() => {
    ready.value =
      true
  })

onMounted(
  async () => {
    /*
     * Restore a valid administrator session
     * if this WebView already has one.
     */
    if (
      isTauriDesktop()
    ) {
      await adminStore
        .refreshStatus()
    }

    if (
      !isLoginPage.value
    ) {
      appStore.loadModels()

      appStore
        .startHealthPolling()
    }
  },
)

onUnmounted(() => {
  appStore.stopHealthPolling()
})

useKeyboard()
</script>

<template>
  <NConfigProvider
    :theme="naiveTheme"
    :theme-overrides="
      themeOverrides
    "
  >
    <NMessageProvider>
      <AuthEventListener />

      <NDialogProvider>
        <NNotificationProvider>
          <div
            v-if="
              nodeVersionLow &&
              ready
            "
            class="
              node-warning-bar
            "
          >
            {{
              t(
                'sidebar.nodeVersionWarning',
                {
                  version:
                    appStore.nodeVersion,
                },
              )
            }}
          </div>

          <div
            v-if="ready"
            class="app-layout"
            :class="{
              'no-sidebar':
                isLoginPage,
            }"
          >
            <button
              v-if="
                !isLoginPage
              "
              class="hamburger-btn"
              @click="
                appStore.toggleSidebar
              "
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                stroke-linecap="round"
              >
                <path
                  d="M4 7h16M4 12h16M4 17h16"
                />
              </svg>
            </button>

            <div
              v-if="
                !isLoginPage &&
                appStore.sidebarOpen
              "
              class="
                mobile-backdrop
              "
              @click="
                appStore.closeSidebar
              "
            />

            <AppSidebar
              v-if="
                !isLoginPage
              "
            />

            <main
              class="app-main"
            >
              <router-view />
            </main>
          </div>

          <SessionSearchModal />

          <DefaultCredentialPrompt />

          <WeComSetupPrompt />

          <!--
            Global local administrator password dialog.
          -->
          <AdminUnlockModal />
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.app-layout {
  display: flex;

  height:
    calc(
      100 *
      var(--vh)
    );

  width: 100vw;

  overflow: hidden;

  &.no-sidebar {
    display: block;
  }
}

.app-main {
  flex: 1;

  min-width: 0;
  min-height: 0;

  overflow-y: auto;

  background-color:
    $bg-primary;

  .no-sidebar & {
    height:
      calc(
        100 *
        var(--vh)
      );
  }
}

.node-warning-bar {
  position: absolute;

  top: 0;
  left: 0;

  width: 100%;

  z-index: 100;

  padding:
    4px 16px;

  font-size: 12px;
  font-weight: 500;

  color: #b45309;

  background-color:
    #fef3c7;

  border-bottom:
    1px solid #fde68a;

  text-align: center;

  line-height: 1.4;
}
</style>
