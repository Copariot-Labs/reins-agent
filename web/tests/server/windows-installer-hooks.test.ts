import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import {
  describe,
  expect,
  it,
} from 'vitest'

describe('Windows installer maintenance hooks', () => {
  const source = readFileSync(
    resolve(process.cwd(), '../desktop/src-tauri/windows/hooks.nsh'),
    'utf8',
  )

  it('stops the Reins app and background task before replacing runtime files', () => {
    const preinstall = source.slice(
      source.indexOf('!macro NSIS_HOOK_PREINSTALL'),
      source.indexOf('!macro NSIS_HOOK_PREUNINSTALL'),
    )

    expect(preinstall).toContain('!insertmacro REINS_STOP_RUNTIME_PROCESSES')
    expect(source).toContain('/End /TN "Reins WeCom Ticket Poller"')
    expect(source).toContain('/IM "Reins.exe"')
    expect(source).toContain('/IM "reins-runtime.exe"')
    expect(source).toContain('/IM "officecli.exe"')
    expect(preinstall.indexOf('REINS_STOP_RUNTIME_PROCESSES'))
      .toBeLessThan(preinstall.indexOf('icacls.exe'))
  })

  it('terminates orphaned private runtimes by install path only', () => {
    expect(source).toContain('Get-CimInstance Win32_Process')
    expect(source).toContain('$$env:LOCALAPPDATA Reins')
    expect(source).toContain('StartsWith($$prefix')
    expect(source).not.toContain('/IM "python.exe"')
    expect(source).not.toContain('/IM "node.exe"')
  })

  it('uses the same shutdown flow before uninstalling', () => {
    const preuninstall = source.slice(
      source.indexOf('!macro NSIS_HOOK_PREUNINSTALL'),
    )

    expect(preuninstall).toContain('!insertmacro REINS_STOP_RUNTIME_PROCESSES')
    expect(preuninstall).toContain('/Delete /TN "Reins WeCom Ticket Poller" /F')
  })
})
