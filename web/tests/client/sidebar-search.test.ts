// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const openSessionSearchMock = vi.hoisted(() => vi.fn())
const mockAppStore = vi.hoisted(() => ({
  sidebarOpen: true,
  sidebarCollapsed: false,
  connected: true,
  serverVersion: 'test',
  latestVersion: '',
  updateAvailable: false,
  updateSupported: false,
  updateError: '',
  clientOutdated: false,
  updating: false,
  toggleSidebar: vi.fn(),
  toggleSidebarCollapsed: vi.fn(),
  closeSidebar: vi.fn(),
  doUpdate: vi.fn(),
  reloadClient: vi.fn(),
}))
const mockChatStore = vi.hoisted(() => ({
  sessions: [],
  sessionsLoaded: true,
  sessionProfileFilter: null,
  activeSessionId: null,
  newChat: vi.fn(() => ({ id: 'new-session' })),
  loadSessions: vi.fn(),
  isSessionLive: vi.fn(() => false),
}))
const mockProfilesStore = vi.hoisted(() => ({
  profiles: [],
  activeProfileName: 'default',
  fetchProfiles: vi.fn(),
}))
const mockAdminStore = vi.hoisted(() => ({
  unlocked: false,
  lock: vi.fn(),
}))
const mockRouter = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}))
const mockRoute = vi.hoisted(() => ({
  name: 'hermes.chat',
  query: {},
  matched: [] as Array<{ meta: Record<string, unknown> }>,
}))

vi.mock('@/composables/useSessionSearch', () => ({
  useSessionSearch: () => ({
    openSessionSearch: openSessionSearchMock,
  }),
}))

vi.mock('@/stores/hermes/app', () => ({
  useAppStore: () => mockAppStore,
}))

vi.mock('@/stores/hermes/chat', () => ({
  useChatStore: () => mockChatStore,
}))

vi.mock('@/stores/hermes/profiles', () => ({
  useProfilesStore: () => mockProfilesStore,
}))

vi.mock('@/stores/reins/admin-access', () => ({
  useAdminAccessStore: () => mockAdminStore,
}))

vi.mock('@/api/client', () => ({
  isStoredSuperAdmin: () => true,
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    useRoute: () => mockRoute,
    useRouter: () => mockRouter,
  }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: { value: 'en' },
  }),
  createI18n: () => ({
    global: { locale: { value: 'en' }, setLocaleMessage: vi.fn() },
  }),
}))

vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({ isDark: false }),
}))

vi.mock('/logo.jpg', () => ({
  default: 'logo.jpg',
}))

vi.mock('@/components/layout/ProfileSelector.vue', () => ({
  default: { name: 'ProfileSelector', template: '<div />' },
}))

vi.mock('@/components/layout/ModelSelector.vue', () => ({
  default: { name: 'ModelSelector', template: '<div />' },
}))

vi.mock('@/components/layout/LanguageSwitch.vue', () => ({
  default: { name: 'LanguageSwitch', template: '<div />' },
}))

vi.mock('@/components/layout/ThemeSwitch.vue', () => ({
  default: { name: 'ThemeSwitch', template: '<div />' },
}))

vi.mock('@/components/common/RouteLinkItem.vue', () => ({
  default: {
    name: 'RouteLinkItem',
    props: ['to', 'active'],
    template: '<a class="route-link-item" :class="{ active }" href="#"><slot /></a>',
  },
}))

vi.mock('naive-ui', async () => {
  const actual = await vi.importActual<any>('naive-ui')
  return {
    ...actual,
    useMessage: () => ({
      success: vi.fn(),
      error: vi.fn(),
    }),
    NButton: {
      template: '<button v-bind="$attrs"><slot /></button>',
    },
    NSelect: {
      template: '<div />',
    },
  }
})

import AppSidebar from '@/components/layout/AppSidebar.vue'

describe('AppSidebar search entry', () => {
  beforeEach(() => {
    openSessionSearchMock.mockClear()
    mockAppStore.serverVersion = 'test'
    mockAppStore.latestVersion = ''
    mockAppStore.updateAvailable = false
    mockAppStore.updateSupported = false
    mockAppStore.updateError = ''
    mockAppStore.clientOutdated = false
    mockAppStore.updating = false
    mockAppStore.sidebarCollapsed = false
    mockAppStore.toggleSidebarCollapsed.mockClear()
    mockAppStore.reloadClient.mockClear()
    mockAppStore.doUpdate.mockReset()
    mockAdminStore.unlocked = false
    mockAdminStore.lock.mockReset()
    mockRouter.replace.mockReset()
    mockRoute.name = 'hermes.chat'
    mockRoute.query = {}
    mockRoute.matched = []
  })

  it('opens the session search modal from the sidebar button', async () => {
    const wrapper = mount(AppSidebar, {
      global: {
        stubs: {
          ProfileSelector: true,
          ModelSelector: true,
          LanguageSwitch: true,
          ThemeSwitch: true,
          NButton: true,
        },
      },
    })

    const buttons = wrapper.findAll('button')
    const searchButton = buttons.find(node => node.text().includes('sidebar.search'))
    expect(searchButton).toBeTruthy()

    await searchButton!.trigger('click')
    expect(openSessionSearchMock).toHaveBeenCalledTimes(1)
  })

  it('shows Word, Excel, and PPT as the direct Office work categories', () => {
    mockRoute.name = 'hermes.office'
    mockRoute.query = { type: 'xlsx' }

    const wrapper = mount(AppSidebar, {
      global: {
        stubs: {
          LanguageSwitch: true,
          ThemeSwitch: true,
        },
      },
    })

    expect(wrapper.get('.office-parent').attributes('aria-expanded')).toBe('true')

    const categories = wrapper.findAll('.office-subitem')
    expect(categories.map(item => item.findAll('span').at(-1)?.text())).toEqual([
      'Word documents',
      'Excel workbooks',
      'PPT presentations',
    ])
    expect(categories.map(item => item.classes().includes('active'))).toEqual([
      false,
      true,
      false,
    ])
  })

  it('collapses to the compact icon rail', async () => {
    mockAppStore.sidebarCollapsed = true
    const wrapper = mount(AppSidebar, {
      global: {
        stubs: {
          ProfileSelector: true,
          ModelSelector: true,
          LanguageSwitch: true,
          ThemeSwitch: true,
          NButton: true,
        },
      },
    })

    expect(wrapper.classes()).toContain('collapsed')
    const restoreButton = wrapper.find('.collapse-btn')
    expect(restoreButton.exists()).toBe(true)
    expect(restoreButton.attributes('aria-expanded')).toBe('false')
    await restoreButton.trigger('click')
    expect(mockAppStore.toggleSidebarCollapsed).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.primary-nav').exists()).toBe(true)
    expect(wrapper.find('.task-section').exists()).toBe(true)
    expect(wrapper.find('.utility-sections').exists()).toBe(true)
  })

  it('logs out of administrator access and leaves a protected page', async () => {
    mockAdminStore.unlocked = true
    mockRoute.name = 'hermes.settings'
    mockRoute.matched = [{
      meta: {
        requiresDesktopAdmin: true,
      },
    }]
    const wrapper = mount(AppSidebar, {
      global: {
        stubs: {
          LanguageSwitch: true,
          ThemeSwitch: true,
        },
      },
    })

    const logout = wrapper.find('.admin-logout')
    expect(logout.exists()).toBe(true)
    await logout.trigger('click')

    expect(mockAdminStore.lock).toHaveBeenCalledTimes(1)
    expect(mockRouter.replace).toHaveBeenCalledWith({
      name: 'hermes.chat',
    })
  })
})
