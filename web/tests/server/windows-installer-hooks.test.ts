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

  it('routes an interactive version upgrade around the broken legacy uninstaller', () => {
    const guiInit = source.slice(
      source.indexOf('Function ReinsUpgradeRecoveryGuiInit'),
      source.indexOf('!macro REINS_PAUSE_BACKGROUND_TASK'),
    )

    expect(source).toContain(
      '!define MUI_CUSTOMFUNCTION_GUIINIT ReinsUpgradeRecoveryGuiInit',
    )
    expect(source).toContain(
      '!define MUI_CUSTOMFUNCTION_ABORT ReinsUpgradeRecoveryAbort',
    )
    expect(source).not.toContain('Function .onGUIInit')
    expect(source).not.toContain('Function .onUserAbort')
    expect(guiInit).toContain('${GetFileVersion} "$EXEPATH" $0')
    expect(guiInit).toContain('${VersionCompare} "$0" "$1" $2')
    expect(guiInit).toContain('StrCmp $1 "0.1.9"')
    expect(source).toContain('!macro REINS_RESTORE_UPGRADE_VERSION')
    expect(source).toContain('Function ReinsUpgradeRecoveryAbort')
    expect(source).toContain('Function .onInstFailed')
    expect(source).toContain('ReinsUpgradeRecoveryVersion')
    expect(guiInit).toContain(
      'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Reins',
    )
    expect(guiInit).toContain('WriteRegStr HKCU')
  })

  it('terminates orphaned private runtimes by install path only', () => {
    expect(source).toContain('Get-CimInstance Win32_Process')
    expect(source).toContain('Join-Path (Join-Path $$env:LOCALAPPDATA Reins) runtime')
    expect(source).toContain('StartsWith($$prefix')
    expect(source).toContain('AddSeconds(20)')
    expect(source).toContain('do { $$processes = @(')
    expect(source).not.toContain(
      '$$root = [IO.Path]::GetFullPath((Join-Path $$env:LOCALAPPDATA Reins))',
    )
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
      source.indexOf('!macro NSIS_HOOK_POSTUNINSTALL'),
    )
    const postuninstall = source.slice(
      source.indexOf('!macro NSIS_HOOK_POSTUNINSTALL'),
    )

    expect(preuninstall).toContain('!insertmacro REINS_STOP_RUNTIME_PROCESSES')
    expect(preuninstall).toContain('/Delete /TN "Reins WeCom Ticket Poller" /F')
    expect(preuninstall).not.toContain('Abort')
    expect(postuninstall).toContain(
      'RMDir /r /REBOOTOK "$LOCALAPPDATA\\Reins\\runtime"',
    )
  })

  it('aborts an upgrade only when a bundled runtime process remains', () => {
    const preinstall = source.slice(
      source.indexOf('!macro NSIS_HOOK_PREINSTALL'),
      source.indexOf('!macro NSIS_HOOK_POSTINSTALL'),
    )

    expect(preinstall).toContain('StrCmp $0 "0" +3 0')
    expect(preinstall).toContain('Abort')
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

describe('Windows installer release smoke test', () => {
  const source = readFileSync(
    resolve(process.cwd(), '../scripts/test-windows-installer.ps1'),
    'utf8',
  )
  const workflow = readFileSync(
    resolve(process.cwd(), '../.github/workflows/windows-desktop.yml'),
    'utf8',
  )

  it('tests clean install, locked-runtime upgrade, uninstall, and reinstall before publishing', () => {
    expect(source).toContain('Starting Reins to lock its private runtime')
    expect(source).toContain('@("/S", "/NS", "/UPDATE")')
    expect(source).toContain('$UninstallerPath')
    expect(source).toContain('Reinstalling Reins after Windows uninstallation')
    expect(workflow).toContain('./scripts/test-windows-installer.ps1')
    expect(workflow.indexOf('./scripts/test-windows-installer.ps1')).toBeLessThan(
      workflow.indexOf('Sign installer when a certificate is configured'),
    )
  })
})
