// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { useProfilesStore } from '@/stores/hermes/profiles'
import { useChatCapabilitiesStore } from '@/stores/hermes/chat-capabilities'

describe('chat capabilities store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.localStorage.clear()
  })

  it('defaults to backend browsing and computer use off', () => {
    const profilesStore = useProfilesStore()
    profilesStore.activeProfileName = 'default'

    const store = useChatCapabilitiesStore()

    expect(store.snapshot).toEqual({
      browser: { mode: 'backend' },
      computer_use: { enabled: false },
    })
  })

  it('persists capability modes per profile', async () => {
    const profilesStore = useProfilesStore()
    profilesStore.activeProfileName = 'default'
    const store = useChatCapabilitiesStore()

    store.browserMode = 'connected'
    store.computerUseEnabled = true

    expect(JSON.parse(window.localStorage.getItem('reins_chat_capabilities_v1_default') || '{}')).toEqual({
      browser: { mode: 'connected' },
      computer_use: { enabled: true },
    })

    window.localStorage.setItem('reins_chat_capabilities_v1_work', JSON.stringify({
      browser: { mode: 'off' },
      computer_use: { enabled: false },
    }))

    profilesStore.activeProfileName = 'work'
    await nextTick()

    expect(store.profileName).toBe('work')
    expect(store.snapshot).toEqual({
      browser: { mode: 'off' },
      computer_use: { enabled: false },
    })

    profilesStore.activeProfileName = 'default'
    await nextTick()

    expect(store.snapshot).toEqual({
      browser: { mode: 'connected' },
      computer_use: { enabled: true },
    })
  })
})
