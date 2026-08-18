<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'
import { useAppStore } from '@/stores/hermes/app'
import { useChatStore } from '@/stores/hermes/chat'
import { useProfilesStore } from '@/stores/hermes/profiles'
import { useSessionSearch } from '@/composables/useSessionSearch'
import RouteLinkItem from '@/components/common/RouteLinkItem.vue'
import ProfileSelector from './ProfileSelector.vue'
import LanguageSwitch from './LanguageSwitch.vue'
import ThemeSwitch from './ThemeSwitch.vue'
import { isStoredSuperAdmin } from '@/api/client'
import { formatTimestampMs } from '@/shared/session-display'

const { t, locale } = useI18n()
const message = useMessage()
const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const chatStore = useChatStore()
const profilesStore = useProfilesStore()
const { openSessionSearch } = useSessionSearch()

const isSuperAdmin = computed(() => isStoredSuperAdmin())
const selectedKey = computed(() => {
  if (route.name === 'hermes.session') return 'hermes.chat'
  return String(route.name || '')
})
const isChinese = computed(() => locale.value.toLowerCase().startsWith('zh'))
const copy = computed(() => isChinese.value
  ? {
      newTask: '新建任务',
      workspace: '工作台',
      assistant: '助手',
      office: 'Office',
      tasks: '任务',
      noTasks: '暂无任务',
      monitoring: '监控',
      system: '系统',
    }
  : {
      newTask: 'New Task',
      workspace: 'Workspace',
      assistant: 'Assistant',
      office: 'Office',
      tasks: 'Tasks',
      noTasks: 'No tasks yet',
      monitoring: 'Monitoring',
      system: 'System',
    })

const recentSessions = computed(() => [...chatStore.sessions]
  .sort((a, b) => (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0))
  .slice(0, 30))

// function isNavActive(...names: string[]) {
//   return names.includes(selectedKey.value)
// }

async function startNewTask() {
  chatStore.clearActiveSession()
  await router.push({ name: 'hermes.chat' })
}

async function openSession(sessionId: string) {
  if (chatStore.activeSessionId === sessionId && route.name === 'hermes.session') return
  await router.push({ name: 'hermes.session', params: { sessionId } })
}

async function handleUpdate() {
  message.success(t('sidebar.updateSuccess'), { duration: 5000 })
  const ok = await appStore.doUpdate()
  if (!ok) message.error(appStore.updateError || t('sidebar.updateFailed'), { duration: 8000 })
}

function handleLogout() {
  localStorage.clear()
  router.replace({ name: 'login' })
}

onMounted(async () => {
  if (profilesStore.profiles.length === 0) await profilesStore.fetchProfiles()
  if (!chatStore.sessionsLoaded) await chatStore.loadSessions(chatStore.sessionProfileFilter)
})
</script>

<template>
  <aside class="sidebar" :class="{ open: appStore.sidebarOpen, collapsed: appStore.sidebarCollapsed }">
    <div class="sidebar-brand-row">
      <RouteLinkItem class="sidebar-logo" :to="{ name: 'hermes.chat' }">
        <img src="/logo.jpg" alt="Reins" class="brand-mark" />
        <span class="logo-text">Reins</span>
      </RouteLinkItem>
      <button
        class="collapse-btn"
        type="button"
        :aria-expanded="!appStore.sidebarCollapsed"
        :title="appStore.sidebarCollapsed ? t('sidebar.expand') : t('sidebar.collapse')"
        @click="appStore.toggleSidebarCollapsed()"
      >
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M9 4v16" />
        </svg>
      </button>
    </div>

    <!-- <button class="new-task-button" type="button" @click="startNewTask">
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a3 3 0 0 1-3 3H8l-5 3V6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3z" />
        <path d="M12 7v6M9 10h6" />
      </svg>
      <span>{{ copy.newTask }}</span>
    </button>  -->
    <nav class="primary-nav" :aria-label="copy.workspace">
      <RouteLinkItem class="nav-item compact" :to="{name: 'hermes.chat'}" type="button" @click="startNewTask">
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a3 3 0 0 1-3 3H8l-5 3V6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3z" />
        <path d="M12 7v6M9 10h6" />
      </svg>
      <span>{{ copy.newTask }}</span>
    </RouteLinkItem> 
      <!-- <RouteLinkItem class="nav-item compact" :to="{ name: 'hermes.chat' }" :active="isNavActive('hermes.chat')" @click="startNewTask">
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a3 3 0 0 1-3 3H8l-5 3V6a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3z" />
        <path d="M12 7v6M9 10h6" />
      </svg>
        <span>{{ copy.newTask }}</span>
      </RouteLinkItem> -->

      <RouteLinkItem class="nav-item compact" :to="{ name: 'hermes.office' }" :active="selectedKey === 'hermes.office'">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 3h8l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
          <path d="M14 3v5h5M8 13h6M8 17h6" />
        </svg>
        <span>{{ copy.office }}</span>
      </RouteLinkItem>

      <button class="nav-item" type="button" @click="openSessionSearch">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
        <span>{{ t('sidebar.search') }}</span>
      </button>
    </nav>

    <section class="task-section">
      <div class="section-label">
        <span>{{ copy.tasks }}</span>
        <span v-if="recentSessions.length" class="section-count">{{ recentSessions.length }}</span>
      </div>
      <div class="task-list">
        <button
          v-for="session in recentSessions"
          :key="session.id"
          class="task-row"
          :class="{ active: session.id === chatStore.activeSessionId }"
          type="button"
          @click="openSession(session.id)"
        >
          <span class="task-copy">
            <strong>{{ session.title || copy.newTask }}</strong>
            <small>{{ formatTimestampMs(session.updatedAt || session.createdAt) }}</small>
          </span>
          <span v-if="chatStore.isSessionLive(session.id)" class="task-running" aria-label="Running" />
        </button>
        <div v-if="!recentSessions.length" class="task-empty">{{ copy.noTasks }}</div>
      </div>
    </section>

    <div class="utility-sections">
      <section class="utility-section">
        <div class="section-label">{{ copy.monitoring }}</div>
        <RouteLinkItem class="nav-item compact" :to="{ name: 'hermes.finance' }" :active="selectedKey === 'hermes.finance'">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
          </svg>
          <span>{{ t('sidebar.finance') }}</span>
        </RouteLinkItem>
        <RouteLinkItem class="nav-item compact" :to="{ name: 'hermes.workOrders' }" :active="selectedKey === 'hermes.workOrders'">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 3h14a2 2 0 0 1 2 2v16H3V5a2 2 0 0 1 2-2zM8 8h8M8 12h5" />
            <path d="m15 17 2 2 4-4" />
          </svg>
          <span>{{ t('sidebar.workOrders') }}</span>
        </RouteLinkItem>
      </section>

      <section class="utility-section">
        <div class="section-label">{{ copy.system }}</div>
        <RouteLinkItem v-if="isSuperAdmin" class="nav-item compact" :to="{ name: 'hermes.profiles' }" :active="selectedKey === 'hermes.profiles'">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
            <circle cx="12" cy="7" r="4" /><path d="M4 21a8 8 0 0 1 16 0" />
          </svg>
          <span>{{ t('sidebar.profiles') }}</span>
        </RouteLinkItem>
        <RouteLinkItem class="nav-item compact" :to="{ name: 'hermes.settings' }" :active="selectedKey === 'hermes.settings'">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1-2.9 2.9-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21h-4v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1-2.9-2.9.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3v-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1 2.9-2.9.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.5V3h4v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1 2.9 2.9-.1.1a1.7 1.7 0 0 0-.3 1.8 1.7 1.7 0 0 0 1.5 1h.1v4h-.1a1.7 1.7 0 0 0-1.5 1z" />
          </svg>
          <span>{{ t('sidebar.settings') }}</span>
        </RouteLinkItem>

        <!-- Model -->
         <RouteLinkItem class="nav-item compact" :to="{ name: 'hermes.models' }" :active="selectedKey === 'hermes.models'">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v4" />
              <path d="M12 19v4" />
              <path d="M1 12h4" />
              <path d="M19 12h4" />
              <path d="M4.22 4.22l2.83 2.83" />
              <path d="M16.95 16.95l2.83 2.83" />
              <path d="M4.22 19.78l2.83-2.83" />
              <path d="M16.95 7.05l2.83-2.83" />
            </svg>
            <span>{{ t("sidebar.models") }}</span>
          </RouteLinkItem>
      </section>
    </div>

    <ProfileSelector />

    <div class="sidebar-footer">
      <div class="status-row">
        <span class="status-dot" :class="{ connected: appStore.connected }" />
        <span>{{ appStore.connected ? t('sidebar.connected') : t('sidebar.disconnected') }}</span>
        <LanguageSwitch />
        <ThemeSwitch />
      </div>
      <div class="footer-actions">
        <button type="button" :disabled="appStore.updating" @click="handleUpdate">{{ appStore.updating ? t('sidebar.updating') : t('common.update') }}</button>
        <button type="button" @click="handleLogout">{{ t('sidebar.logout') }}</button>
      </div>
    </div>
  </aside>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.sidebar {
  position: relative;
  width: 272px;
  height: calc(100 * var(--vh));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  padding: 14px 12px 12px;
  overflow: hidden;
  color: $text-primary;
  background: $bg-sidebar;
  border-right: 1px solid $border-color;
  transition: width $transition-normal;
}

.sidebar-brand-row,
.sidebar-logo,
.status-row,
.footer-actions,
.section-label {
  display: flex;
  align-items: center;
}

.sidebar-brand-row {
  height: 42px;
  justify-content: space-between;
  padding: 0 6px 6px;
}

.sidebar-logo {
  min-width: 0;
  gap: 9px;
  color: inherit;
}

.brand-mark {
  width: 27px;
  height: 27px;
  border-radius: 8px;
  object-fit: cover;
}

.logo-text {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -.02em;
}

.version-text {
  color: $text-muted;
  font-size: 11px;
}

.collapse-btn,
.new-task-button,
.nav-item,
.task-row,
.footer-actions button {
  border: 0;
  color: inherit;
  background: transparent;
  font: inherit;
  cursor: pointer;
}

.collapse-btn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: $text-muted;
}

.collapse-btn:hover,
.footer-actions button:hover {
  color: $text-primary;
  background: rgba(var(--accent-primary-rgb), .07);
}

.new-task-button {
  width: 100%;
  height: 48px;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0 10px;
  padding: 0 10px;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 650;
  background: rgba(var(--accent-primary-rgb), .08);
  transition: background .15s ease, transform .15s ease;
}

.new-task-button:hover {
  background: rgba(var(--accent-primary-rgb), .13);
  transform: translateY(-1px);
}

.primary-nav,
.utility-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  width: 100%;
  min-height: 41px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 13px;
  border-radius: 11px;
  color: $text-secondary;
  text-align: left;
  text-decoration: none;
  transition: color .15s ease, background .15s ease;
}

.nav-item:hover,
.nav-item.active {
  color: $text-primary;
  background: rgba(var(--accent-primary-rgb), .075);
}

.nav-item.active {
  font-weight: 600;
}

.nav-item.compact {
  min-height: 34px;
  font-size: 12px;
}

.task-section {
  flex: 1 1 180px;
  display: flex;
  flex-direction: column;
  min-height: 90px;
  margin-top: 14px;
  overflow: hidden;
}

.section-label {
  min-height: 28px;
  justify-content: space-between;
  padding: 0 11px;
  color: $text-muted;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.section-count {
  font-weight: 500;
}

.task-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: none;
}

.task-list::-webkit-scrollbar { display: none; }

.task-row {
  width: 100%;
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 11px;
  border-radius: 10px;
  text-align: left;
}

.task-row:hover,
.task-row.active {
  background: rgba(var(--accent-primary-rgb), .075);
}

.task-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.task-copy strong,
.task-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-copy strong { font-size: 12px; font-weight: 560; }
.task-copy small { color: $text-muted; font-size: 10px; }

.task-running {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: $success;
  box-shadow: 0 0 0 3px rgba(var(--success-rgb), .12);
}

.task-empty {
  padding: 16px 11px;
  color: $text-muted;
  font-size: 12px;
}

.utility-sections {
  flex: 0 0 auto;
  max-height: 260px;
  overflow-y: auto;
  padding-top: 8px;
  border-top: 1px solid $border-color;
}

.utility-section + .utility-section { margin-top: 5px; }

:deep(.profile-selector) {
  flex: 0 0 auto;
  padding-top: 10px;
  border-top: 1px solid $border-color;
}

.sidebar-footer {
  flex: 0 0 auto;
  padding: 8px 4px 0;
}

.status-row {
  gap: 7px;
  color: $text-muted;
  font-size: 10px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: $error;
}

.status-dot.connected { background: $success; }
.status-row :deep(.language-switch) { margin-left: auto; }

.footer-actions {
  justify-content: space-between;
  margin-top: 4px;
}

.footer-actions button {
  padding: 4px 7px;
  border-radius: 6px;
  color: $text-muted;
  font-size: 10px;
}

.sidebar.collapsed {
  width: 70px;
  padding-inline: 9px;
}

.sidebar.collapsed .logo-text,
.sidebar.collapsed .version-text,
.sidebar.collapsed .new-task-button span,
.sidebar.collapsed .nav-item span,
.sidebar.collapsed .task-section,
.sidebar.collapsed .utility-sections,
.sidebar.collapsed .sidebar-footer {
  display: none;
}

.sidebar.collapsed .sidebar-brand-row { justify-content: center; padding-inline: 0; }
.sidebar.collapsed .sidebar-logo { display: none; }
.sidebar.collapsed .collapse-btn { display: grid; flex: 0 0 30px; }
.sidebar.collapsed .new-task-button,
.sidebar.collapsed .nav-item { justify-content: center; padding: 0; }
.sidebar.collapsed :deep(.profile-selector .selector-label),
.sidebar.collapsed :deep(.profile-selector .profile-name) { display: none; }

@media (max-width: $breakpoint-mobile) {
  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 1000;
    width: min(300px, 86vw);
    transform: translateX(-100%);
    box-shadow: 16px 0 40px rgba(0, 0, 0, .12);
  }

  .sidebar.open { transform: translateX(0); }
  .sidebar.collapsed { width: min(300px, 86vw); }
  .sidebar.collapsed .logo-text,
  .sidebar.collapsed .version-text,
  .sidebar.collapsed .new-task-button span,
  .sidebar.collapsed .nav-item span { display: inline; }
  .sidebar.collapsed .task-section { display: flex; }
  .sidebar.collapsed .utility-sections,
  .sidebar.collapsed .sidebar-footer { display: block; }
  .sidebar.collapsed .new-task-button,
  .sidebar.collapsed .nav-item { justify-content: flex-start; padding: 0 13px; }
  .sidebar.collapsed .sidebar-logo { display: flex; }
  .sidebar.collapsed :deep(.profile-selector .selector-label),
  .sidebar.collapsed :deep(.profile-selector .profile-name) { display: block; }
}
</style>
