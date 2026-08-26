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
      source.indexOf('!macro NSIS_HOOK_POSTINSTALL'),
    )

    expect(preinstall).toContain('!insertmacro REINS_STOP_RUNTIME_PROCESSES')
    expect(source).toContain('Disable-ScheduledTask')
    expect(source).toContain('/Change /TN "Reins WeCom Ticket Poller" /DISABLE')
    expect(source).toContain('/End /TN "Reins WeCom Ticket Poller"')
    expect(source.indexOf('/DISABLE'))
      .toBeLessThan(source.indexOf('/End /TN "Reins WeCom Ticket Poller"'))
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
    expect(source).toContain('AddSeconds(20)')
    expect(source).toContain('do { $$processes = @(')
    expect(source).not.toContain('/IM "python.exe"')
    expect(source).not.toContain('/IM "node.exe"')
  })

  it('restores an enabled background task only after the upgrade completes', () => {
    const postinstall = source.slice(
      source.indexOf('!macro NSIS_HOOK_POSTINSTALL'),
      source.indexOf('!macro NSIS_HOOK_PREUNINSTALL'),
    )

    expect(source).toContain('reins-poller-was-enabled')
    expect(postinstall).toContain('!insertmacro REINS_RESUME_BACKGROUND_TASK')
    expect(source).toContain('Enable-ScheduledTask')
    expect(source).toContain('Start-ScheduledTask')
  })

  it('uses the same shutdown flow before uninstalling', () => {
    const preuninstall = source.slice(
      source.indexOf('!macro NSIS_HOOK_PREUNINSTALL'),
    )

    expect(preuninstall).toContain('!insertmacro REINS_STOP_RUNTIME_PROCESSES')
    expect(preuninstall).toContain('/Delete /TN "Reins WeCom Ticket Poller" /F')
  })
})

describe('Windows desktop backend shutdown', () => {
  const source = readFileSync(
    resolve(process.cwd(), '../desktop/src-tauri/src/lib.rs'),
    'utf8',
  )

  it('terminates the complete Node and Python process tree', () => {
    expect(source).toContain('Command::new("taskkill.exe")')
    expect(source).toContain('.args(["/PID", pid.as_str(), "/T", "/F"])')
  })
})
