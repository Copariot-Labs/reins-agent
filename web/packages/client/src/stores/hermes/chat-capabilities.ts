import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useProfilesStore } from './profiles'
import type { ChatCapabilities } from '@/api/hermes/chat'

export type BrowserCapabilityMode = 'off' | 'backend' | 'connected'

const STORAGE_KEY_PREFIX = 'reins_chat_capabilities_v1_'

const DEFAULT_CAPABILITIES: ChatCapabilities = {
  browser: { mode: 'backend' },
  computer_use: { enabled: false },
}

function currentProfileName(): string {
  try {
    return useProfilesStore().activeProfileName || 'default'
  } catch {
    return localStorage.getItem('hermes_active_profile_name') || 'default'
  }
}

function storageKey(profileName: string): string {
  return `${STORAGE_KEY_PREFIX}${profileName}`
}

function normalizeBrowserMode(value: unknown): BrowserCapabilityMode {
  return value === 'off' || value === 'connected' ? value : 'backend'
}

function normalizeCapabilities(value: unknown): ChatCapabilities {
  const record = value && typeof value === 'object' ? value as Record<string, any> : {}
  const browser = record.browser && typeof record.browser === 'object' ? record.browser : {}
  const computerUse = record.computer_use && typeof record.computer_use === 'object' ? record.computer_use : {}
  return {
    browser: {
      mode: normalizeBrowserMode(browser.mode),
    },
    computer_use: {
      enabled: computerUse.enabled === true,
    },
  }
}

function loadCapabilities(profileName: string): ChatCapabilities {
  try {
    const raw = localStorage.getItem(storageKey(profileName))
    return raw ? normalizeCapabilities(JSON.parse(raw)) : { ...DEFAULT_CAPABILITIES, browser: { ...DEFAULT_CAPABILITIES.browser }, computer_use: { ...DEFAULT_CAPABILITIES.computer_use } }
  } catch {
    return { ...DEFAULT_CAPABILITIES, browser: { ...DEFAULT_CAPABILITIES.browser }, computer_use: { ...DEFAULT_CAPABILITIES.computer_use } }
  }
}

function saveCapabilities(profileName: string, value: ChatCapabilities) {
  try {
    localStorage.setItem(storageKey(profileName), JSON.stringify(normalizeCapabilities(value)))
  } catch {
    // Storage is best-effort; current in-memory values still apply to the run.
  }
}

export const useChatCapabilitiesStore = defineStore('chat-capabilities', () => {
  const profileName = ref(currentProfileName())
  const capabilities = ref<ChatCapabilities>(loadCapabilities(profileName.value))

  const browserMode = computed({
    get: () => capabilities.value.browser?.mode || 'backend',
    set: (mode: BrowserCapabilityMode) => {
      capabilities.value = normalizeCapabilities({
        ...capabilities.value,
        browser: { ...(capabilities.value.browser || {}), mode },
      })
      persist()
    },
  })

  const computerUseEnabled = computed({
    get: () => capabilities.value.computer_use?.enabled === true,
    set: (enabled: boolean) => {
      capabilities.value = normalizeCapabilities({
        ...capabilities.value,
        computer_use: { ...(capabilities.value.computer_use || {}), enabled },
      })
      persist()
    },
  })

  const snapshot = computed<ChatCapabilities>(() => normalizeCapabilities(capabilities.value))

  function reload() {
    profileName.value = currentProfileName()
    capabilities.value = loadCapabilities(profileName.value)
  }

  function persist() {
    saveCapabilities(profileName.value, capabilities.value)
  }

  watch(
    () => useProfilesStore().activeProfileName,
    () => reload(),
  )

  return {
    profileName,
    capabilities,
    browserMode,
    computerUseEnabled,
    snapshot,
    reload,
  }
})
