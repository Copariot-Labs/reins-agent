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

vi.mock('@/api/client', () => ({
  isStoredSuperAdmin: () => true,
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    useRoute: () => ({ name: 'hermes.chat' }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
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
    mockAppStore.reloadClient.mockClear()
    mockAppStore.doUpdate.mockReset()
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

  it('starts a managed Reins update from the sidebar', async () => {
    mockAppStore.updateSupported = true
    mockAppStore.doUpdate.mockResolvedValue(true)
    const wrapper = mount(AppSidebar, {
      global: {
        stubs: {
          ProfileSelector: true,
          ModelSelector: true,
          LanguageSwitch: true,
          ThemeSwitch: true,
        },
      },
    })

    const updateButton = wrapper.findAll('button')
      .find(node => node.text().includes('common.update'))
    expect(updateButton).toBeTruthy()

    await updateButton!.trigger('click')
    expect(mockAppStore.doUpdate).toHaveBeenCalledTimes(1)
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
    expect(wrapper.find('.new-task-button').exists()).toBe(true)
    expect(wrapper.find('.task-section').exists()).toBe(true)
    expect(wrapper.find('.utility-sections').exists()).toBe(true)
  })
})
