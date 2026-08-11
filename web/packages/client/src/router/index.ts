import { createRouter, createWebHashHistory } from 'vue-router';
import { hasApiKey, isStoredSuperAdmin } from '@/api/client';

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/reins/chat',
      name: 'hermes.chat',
      component: () => import('@/views/hermes/ChatView.vue'),
    },
    {
      path: '/reins/session/:sessionId',
      name: 'hermes.session',
      component: () => import('@/views/hermes/ChatView.vue'),
    },
    {
      path: '/reins/history',
      name: 'hermes.history',
      component: () => import('@/views/hermes/HistoryView.vue'),
    },
    {
      path: '/reins/history/session/:sessionId',
      name: 'hermes.historySession',
      component: () => import('@/views/hermes/HistoryView.vue'),
    },
    {
      path: '/reins/jobs',
      name: 'hermes.jobs',
      component: () => import('@/views/hermes/JobsView.vue'),
    },
    {
      path: '/reins/workmode',
      redirect: { name: 'hermes.chat' },
    },
    {
      path: '/reins/kanban',
      name: 'hermes.kanban',
      component: () => import('@/views/hermes/KanbanView.vue'),
    },
    {
      path: '/reins/models',
      name: 'hermes.models',
      component: () => import('@/views/hermes/ModelsView.vue'),
    },
    {
      path: '/reins/profiles',
      name: 'hermes.profiles',
      component: () => import('@/views/hermes/ProfilesView.vue'),
      meta: { requiresSuperAdmin: true },
    },
    {
      path: '/reins/logs',
      name: 'hermes.logs',
      component: () => import('@/views/hermes/LogsView.vue'),
    },
    {
      path: '/reins/usage',
      name: 'hermes.usage',
      component: () => import('@/views/hermes/UsageView.vue'),
    },
    {
      path: '/reins/finance',
      name: 'hermes.finance',
      component: () => import('@/views/hermes/FinanceView.vue'),
    },
    {
      path: '/reins/office',
      name: 'hermes.office',
      component: () => import('@/views/reins/OfficeView.vue'),
    },
    {
      path: '/reins/work-orders',
      name: 'hermes.workOrders',
      component: () => import('@/views/hermes/WorkOrdersView.vue'),
    },
    {
      path: '/reins/presentations',
      name: 'hermes.presentations',
      component: () => import('@/views/hermes/PresentationsView.vue'),
    },
    {
      path: '/reins/performance',
      name: 'hermes.performance',
      component: () => import('@/views/hermes/PerformanceView.vue'),
      meta: { requiresSuperAdmin: true },
    },
    {
      path: '/reins/skills-usage',
      name: 'hermes.skillsUsage',
      component: () => import('@/views/hermes/SkillsUsageView.vue'),
    },
    {
      path: '/reins/skills',
      name: 'hermes.skills',
      component: () => import('@/views/hermes/SkillsView.vue'),
    },
    {
      path: '/reins/plugins',
      name: 'hermes.plugins',
      component: () => import('@/views/hermes/PluginsView.vue'),
    },
    {
      path: '/reins/memory',
      name: 'hermes.memory',
      component: () => import('@/views/hermes/MemoryView.vue'),
    },
    {
      path: '/reins/settings',
      name: 'hermes.settings',
      component: () => import('@/views/hermes/SettingsView.vue'),
    },
    {
      path: '/reins/channels',
      name: 'hermes.channels',
      component: () => import('@/views/hermes/ChannelsView.vue'),
    },
    {
      path: '/reins/terminal',
      name: 'hermes.terminal',
      component: () => import('@/views/hermes/TerminalView.vue'),
    },
    {
      path: '/reins/group-chat',
      name: 'hermes.groupChat',
      component: () => import('@/views/hermes/GroupChatView.vue'),
    },
    {
      path: '/reins/group-chat/room/:roomId',
      name: 'hermes.groupChatRoom',
      component: () => import('@/views/hermes/GroupChatView.vue'),
    },
    {
      path: '/reins/files',
      name: 'hermes.files',
      component: () => import('@/views/hermes/FilesView.vue'),
    },
    {
      path: '/reins/version-preview',
      name: 'hermes.versionPreview',
      component: () => import('@/views/hermes/VersionPreviewView.vue'),
      meta: { requiresSuperAdmin: true },
    },
  ],
});

router.beforeEach((to, _from, next) => {
  // Public pages don't need auth
  if (to.meta.public) {
    // Already has key, skip login
    if (to.name === 'login' && hasApiKey()) {
      next({ path: '/reins/chat' });
      return;
    }
    next();
    return;
  }

  // All other pages require token
  if (!hasApiKey()) {
    next({ name: 'login' });
    return;
  }

  if (to.meta.requiresSuperAdmin && !isStoredSuperAdmin()) {
    next({ name: 'hermes.chat' });
    return;
  }

  next();
});

export default router;
