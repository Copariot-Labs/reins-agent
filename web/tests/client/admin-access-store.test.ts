// @vitest-environment jsdom
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'
import {
  createPinia,
  setActivePinia,
} from 'pinia'

const api = vi.hoisted(() => ({
  clearAdminToken: vi.fn(),
  fetchAdminAccessStatus: vi.fn(),
  getAdminToken: vi.fn(() => ''),
  lockAdminAccess: vi.fn(),
  setupAdminAccess: vi.fn(),
  unlockAdminAccess: vi.fn(),
}))

vi.mock('@/api/reins/admin-access', () => ({
  ...api,
  AdminAccessApiError: class AdminAccessApiError extends Error {
    constructor(
      message: string,
      public readonly code = '',
      public readonly retryAfterSeconds = 0,
    ) {
      super(message)
    }
  },
}))

import { useAdminAccessStore } from '@/stores/reins/admin-access'

describe('administrator access store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api.getAdminToken.mockReturnValue('')
  })

  it('loads configuration before the first route guard opens the dialog', async () => {
    api.fetchAdminAccessStatus.mockResolvedValue({
      configured: true,
      unlocked: false,
      setupAllowed: false,
    })
    const store = useAdminAccessStore()

    await expect(store.ensureUnlocked()).resolves.toBe(false)
    expect(api.fetchAdminAccessStatus).toHaveBeenCalledTimes(1)
    expect(store.initialized).toBe(true)
    expect(store.configured).toBe(true)
  })

  it('sets up and unlocks a local development installation', async () => {
    api.setupAdminAccess.mockResolvedValue({
      ok: true,
      token: 'setup-token',
    })
    const store = useAdminAccessStore()
    store.setupAllowed = true
    store.modalOpen = true

    await expect(store.setup('local development admin')).resolves.toBe(true)
    expect(api.setupAdminAccess).toHaveBeenCalledWith('local development admin')
    expect(store.configured).toBe(true)
    expect(store.unlocked).toBe(true)
    expect(store.setupAllowed).toBe(false)
    expect(store.modalOpen).toBe(false)
  })

  it('revokes the administrator session when the user logs out', async () => {
    api.lockAdminAccess.mockResolvedValue(undefined)
    const store = useAdminAccessStore()
    store.unlocked = true
    store.modalOpen = true

    await store.lock()

    expect(api.lockAdminAccess).toHaveBeenCalledTimes(1)
    expect(store.unlocked).toBe(false)
    expect(store.modalOpen).toBe(false)
  })
})
