import {
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
} from 'vitest'

import {
  configureDevelopmentAdminPassword,
  createAdminPasswordHash,
  createAdminSession,
  getAdminAccessStatus,
  isAdminAccessConfigured,
  isAdminSetupAllowed,
  revokeAdminSession,
  validateAdminSession,
} from '../../packages/server/src/services/reins/admin-access'

const ENV_KEYS = [
  'NODE_ENV',
  'REINS_ADMIN_PASSWORD_HASH',
  'REINS_ADMIN_PASSWORD_HASH_FILE',
  'REINS_DESKTOP',
  'REINS_HOME',
] as const

describe('Reins administrator access', () => {
  const originalEnvironment = new Map<string, string | undefined>()
  let temporaryHome = ''

  beforeEach(() => {
    for (const key of ENV_KEYS) {
      originalEnvironment.set(key, process.env[key])
      delete process.env[key]
    }

    temporaryHome = mkdtempSync(join(tmpdir(), 'reins-admin-access-'))
    process.env.REINS_HOME = temporaryHome
  })

  afterEach(() => {
    rmSync(temporaryHome, {
      recursive: true,
      force: true,
    })

    for (const key of ENV_KEYS) {
      const value = originalEnvironment.get(key)
      if (typeof value === 'undefined') delete process.env[key]
      else process.env[key] = value
    }
  })

  it('validates a build-provided scrypt hash without storing plaintext', () => {
    const password = 'correct horse battery staple'
    process.env.REINS_ADMIN_PASSWORD_HASH = createAdminPasswordHash(password)

    expect(isAdminAccessConfigured()).toBe(true)
    expect(createAdminSession('wrong password')).toBeNull()

    const token = createAdminSession(password)
    expect(token).toBeTruthy()
    expect(validateAdminSession(token!)).toBe(true)
    expect(getAdminAccessStatus(token!)).toMatchObject({
      configured: true,
      unlocked: true,
      setupAllowed: false,
    })

    revokeAdminSession(token!)
    expect(validateAdminSession(token!)).toBe(false)
  })

  it('loads the packaged password hash from an explicit file', () => {
    const hashPath = join(temporaryHome, 'packaged-admin-password.hash')
    writeFileSync(hashPath, `${createAdminPasswordHash('windows admin password')}\n`)
    process.env.REINS_ADMIN_PASSWORD_HASH_FILE = hashPath

    expect(isAdminAccessConfigured()).toBe(true)
    expect(createAdminSession('windows admin password')).toBeTruthy()
  })

  it('allows one-time local setup only in a desktop development build', () => {
    process.env.NODE_ENV = 'development'
    process.env.REINS_DESKTOP = '1'

    expect(isAdminSetupAllowed()).toBe(true)
    expect(configureDevelopmentAdminPassword('short')).toBeNull()

    const token = configureDevelopmentAdminPassword('local development admin')
    expect(token).toBeTruthy()
    expect(isAdminSetupAllowed()).toBe(false)
    expect(readFileSync(join(temporaryHome, 'admin-password.hash'), 'utf8'))
      .toMatch(/^scrypt\$[A-Za-z0-9_-]+\$[A-Za-z0-9_-]+\n$/)
    expect(validateAdminSession(token!)).toBe(true)
  })

  it('fails closed when a production desktop build has no password hash', () => {
    process.env.NODE_ENV = 'production'
    process.env.REINS_DESKTOP = '1'

    expect(getAdminAccessStatus()).toEqual({
      configured: false,
      unlocked: false,
      setupAllowed: false,
    })
    expect(configureDevelopmentAdminPassword('production admin password'))
      .toBeNull()
  })
})
