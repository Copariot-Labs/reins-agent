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
    const runtimeCommand = source
      .split('\n')
      .find(line => line.includes('function q'))

    expect(source).toContain('Get-CimInstance Win32_Process')
    expect(source).toContain("Join-Path $$env:LOCALAPPDATA 'Reins\\runtime'")
    expect(source).toContain('StartsWith($$r')
    expect(source).toContain('AddSeconds(20)')
    expect(source).toContain('function q')
    expect(source).toContain('while ([DateTime]::UtcNow -lt $$d)')
    expect(runtimeCommand).toBeDefined()
    expect(runtimeCommand!.length).toBeLessThan(1024)
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

    expect(preinstall).toContain(
      'StrCmp $0 "0" reins_preinstall_runtime_stopped',
    )
    expect(preinstall).toContain('!insertmacro REINS_RESUME_BACKGROUND_TASK')
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

describe('Windows installer release validation', () => {
  const workflow = readFileSync(
    resolve(process.cwd(), '../.github/workflows/windows-desktop.yml'),
    'utf8',
  )

  it('validates the built setup without launching an interactive dependency installer', () => {
    expect(workflow).toContain('Validate installer artifact')
    expect(workflow).toContain('$versionInfo.ProductVersion')
    expect(workflow).toContain('Installer artifact is unexpectedly small')
    expect(workflow).not.toContain('./scripts/test-windows-installer.ps1')
    expect(workflow.indexOf('Validate installer artifact')).toBeLessThan(
      workflow.indexOf('Sign installer when a certificate is configured'),
    )
  })

  it('publishes manual and tagged builds to GitHub Releases', () => {
    expect(workflow).toContain('Publish installer to GitHub Releases')
    expect(workflow).toContain("github.event_name == 'workflow_dispatch'")
    expect(workflow).toContain('$tag = "desktop-v$version"')
    expect(workflow).toContain('@("--target", $env:GITHUB_SHA)')
  })
})

describe('Windows packaged Office validation', () => {
  const stagingScript = readFileSync(
    resolve(process.cwd(), '../scripts/stage-windows-runtime.ps1'),
    'utf8',
  )

  it('checks the packaged OfficeCLI and private Python brain before bundling', () => {
    expect(stagingScript).toContain('Verifying packaged Reins Office routing')
    expect(stagingScript).toContain('REINS_SERVICE_PYTHON = $RuntimePython')
    expect(stagingScript).toContain('& $PackagedLauncher office doctor --json')
    expect(stagingScript).toContain('$OfficeStatus.reins_command')
  })
})
