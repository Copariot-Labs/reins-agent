import { createRouter, createWebHashHistory } from 'vue-router';

import { hasApiKey, isStoredSuperAdmin, isTauriDesktop } from '@/api/client';

import { useAdminAccessStore } from '@/stores/reins/admin-access';

const router = createRouter({
  history: createWebHashHistory(),

  routes: [
    {
      path: '/',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: {
        public: true,
      },
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

      redirect: {
        name: 'hermes.chat',
      },
    },

    {
      path: '/reins/kanban',

      name: 'hermes.kanban',

      component: () => import('@/views/hermes/KanbanView.vue'),
    },

    /*
     * Administrator-only desktop pages.
     */
    {
      path: '/reins/models',

      name: 'hermes.models',

      component: () => import('@/views/hermes/ModelsView.vue'),

      meta: {
        requiresDesktopAdmin: true,
      },
    },

    {
      path: '/reins/profiles',

      name: 'hermes.profiles',

      component: () => import('@/views/hermes/ProfilesView.vue'),

      meta: {
        requiresSuperAdmin: true,

        requiresDesktopAdmin: true,
      },
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
      path: '/reins/performance',

      name: 'hermes.performance',

      component: () => import('@/views/hermes/PerformanceView.vue'),

      meta: {
        requiresSuperAdmin: true,
      },
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

      meta: {
        requiresDesktopAdmin: true,
      },
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

      meta: {
        requiresSuperAdmin: true,
      },
    },
  ],
});

router.beforeEach(async (to, from, next) => {
  const desktop = isTauriDesktop();

  /*
   * -------------------------------------------------
   * Reins desktop
   * -------------------------------------------------
   *
   * No normal login.
   */
  if (desktop) {
    /*
     * "/" used to be the Login page.
     *
     * Desktop users go directly to Reins.
     */
    if (to.name === 'login') {
      next({
        name: 'hermes.chat',
      });

      return;
    }

    /*
     * Profile / Settings / Models require
     * the local administrator password.
     */
    if (to.meta.requiresDesktopAdmin) {
      const adminStore = useAdminAccessStore();

      const allowed = await adminStore.ensureUnlocked();

      if (!allowed) {
        adminStore.requestUnlock(to.fullPath);

        /*
         * If this is the first route when the
         * application opens, give the UI a real
         * page behind the password dialog.
         */
        if (!from.name) {
          next({
            name: 'hermes.chat',
          });
        } else {
          next(false);
        }

        return;
      }
    }

    next();

    return;
  }

  /*
   * -------------------------------------------------
   * Existing web behavior
   * -------------------------------------------------
   *
   * Keep web login behavior unchanged.
   */

  if (to.meta.public) {
    if (to.name === 'login' && hasApiKey()) {
      next({
        path: '/reins/chat',
      });

      return;
    }

    next();

    return;
  }

  if (!hasApiKey()) {
    next({
      name: 'login',
    });

    return;
  }

  if (to.meta.requiresSuperAdmin && !isStoredSuperAdmin()) {
    next({
      name: 'hermes.chat',
    });

    return;
  }

  next();
});

export default router;
