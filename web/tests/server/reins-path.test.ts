import { describe, expect, it } from 'vitest'

import {
  defaultReinsHome,
  resolveReinsHome,
  resolveRootHomeFromHermes,
} from '../../packages/server/src/services/hermes/reins-path'

describe('reins path helpers', () => {
  it('uses LOCALAPPDATA for the default Windows Reins home', () => {
    expect(defaultReinsHome(
      { LOCALAPPDATA: 'C:\\Users\\Tester\\AppData\\Local' },
      'win32',
    )).toBe('C:\\Users\\Tester\\AppData\\Local\\reins')
  })

  it('falls back to APPDATA on Windows when LOCALAPPDATA is unavailable', () => {
    expect(defaultReinsHome(
      { APPDATA: 'C:\\Users\\Tester\\AppData\\Roaming' },
      'win32',
    )).toBe('C:\\Users\\Tester\\AppData\\Roaming\\reins')
  })

  it('keeps the dot-directory default for macOS and Linux', () => {
    expect(defaultReinsHome({}, 'darwin')).toMatch(/\/\.reins$/)
    expect(defaultReinsHome({}, 'linux')).toMatch(/\/\.reins$/)
  })

  it('resolves Hermes profile homes back to the root data directory', () => {
    expect(resolveRootHomeFromHermes(
      'C:\\Users\\Tester\\AppData\\Local\\reins\\profiles\\work',
      'win32',
    )).toBe('C:\\Users\\Tester\\AppData\\Local\\reins')

    expect(resolveRootHomeFromHermes(
      '/Users/tester/.reins/profiles/work',
      'darwin',
    )).toBe('/Users/tester/.reins')
  })

  it('prefers explicit REINS_HOME over HERMES_HOME', () => {
    expect(resolveReinsHome(
      {
        REINS_HOME: 'C:\\Reins',
        HERMES_HOME: 'C:\\Other\\profiles\\work',
      },
      'win32',
    )).toBe('C:\\Reins')
  })

  it('expands configured environment variables before resolving homes', () => {
    expect(resolveReinsHome(
      {
        LOCALAPPDATA: 'C:\\Users\\Tester\\AppData\\Local',
        REINS_HOME: '%LOCALAPPDATA%\\reins-dev',
      },
      'win32',
    )).toBe('C:\\Users\\Tester\\AppData\\Local\\reins-dev')

    expect(resolveReinsHome(
      {
        HOME: '/Users/tester',
        REINS_HOME: '$HOME/reins-dev',
      },
      'darwin',
    )).toBe('/Users/tester/reins-dev')
  })
})
