; Tauri normally defaults a version upgrade to running the installed
; uninstaller first. Reins 0.1.9 shipped an uninstaller whose process sweep
; could include the uninstaller itself, so that route cannot repair it.
; Present interactive upgrades as a same-version maintenance install instead;
; Tauri then defaults to replacing the application in place. The normal
; install section still writes the real new DisplayVersion after it succeeds.
!define MUI_CUSTOMFUNCTION_GUIINIT ReinsUpgradeRecoveryGuiInit
!define MUI_CUSTOMFUNCTION_ABORT ReinsUpgradeRecoveryAbort

!macro REINS_RESTORE_UPGRADE_VERSION
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Reins" "ReinsUpgradeRecoveryVersion"
  StrCmp $0 "" +2 0
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Reins" "DisplayVersion" "$0"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Reins" "ReinsUpgradeRecoveryVersion"
!macroend

Function ReinsUpgradeRecoveryGuiInit
  ; Recover the real installed version if an earlier repair was cancelled or
  ; interrupted before the installer could run its normal completion hooks.
  !insertmacro REINS_RESTORE_UPGRADE_VERSION

  ${GetFileVersion} "$EXEPATH" $0
  StrCmp $0 "" reins_upgrade_recovery_done
  StrLen $1 $0
  reins_upgrade_recovery_find_build:
    IntOp $1 $1 - 1
    StrCpy $2 $0 1 $1
    StrCmp $2 "." reins_upgrade_recovery_version_ready reins_upgrade_recovery_find_build
  reins_upgrade_recovery_version_ready:
    StrCpy $0 $0 $1

  ReadRegStr $1 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Reins" "DisplayVersion"
  ; Only 0.1.9 needs this bridge. Later versions contain the corrected
  ; uninstaller and can use Tauri's normal upgrade choices.
  StrCmp $1 "0.1.9" 0 reins_upgrade_recovery_done
  ${VersionCompare} "$0" "$1" $2
  StrCmp $2 "1" 0 reins_upgrade_recovery_done
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Reins" "ReinsUpgradeRecoveryVersion" "$1"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Reins" "DisplayVersion" "$0"

  reins_upgrade_recovery_done:
FunctionEnd

Function ReinsUpgradeRecoveryAbort
  !insertmacro REINS_RESTORE_UPGRADE_VERSION
FunctionEnd

Function .onInstFailed
  !insertmacro REINS_RESTORE_UPGRADE_VERSION
FunctionEnd

!macro REINS_PAUSE_BACKGROUND_TASK
  DetailPrint "Pausing the Reins background task..."

  ; Remember whether the task was enabled so an upgrade can restore its prior
  ; state after all runtime files have been replaced.
  nsExec::ExecToLog `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "& { $$marker = [IO.Path]::Combine('$PLUGINSDIR', 'reins-poller-was-enabled'); Remove-Item -LiteralPath $$marker -Force -ErrorAction SilentlyContinue; $$task = Get-ScheduledTask -TaskName 'Reins WeCom Ticket Poller' -ErrorAction SilentlyContinue; if ($$null -ne $$task) { if ($$task.State -ne 'Disabled') { [IO.File]::WriteAllText($$marker, '1') }; Disable-ScheduledTask -InputObject $$task -ErrorAction SilentlyContinue | Out-Null; Stop-ScheduledTask -InputObject $$task -ErrorAction SilentlyContinue } }"`
  Pop $0

  ; Keep this fallback for Windows editions where the ScheduledTasks
  ; PowerShell module is unavailable.
  nsExec::ExecToLog '"$SYSDIR\schtasks.exe" /Change /TN "Reins WeCom Ticket Poller" /DISABLE'
  Pop $0
  nsExec::ExecToLog '"$SYSDIR\schtasks.exe" /End /TN "Reins WeCom Ticket Poller"'
  Pop $0
!macroend

!macro REINS_RESUME_BACKGROUND_TASK
  nsExec::ExecToLog `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "& { $$marker = [IO.Path]::Combine('$PLUGINSDIR', 'reins-poller-was-enabled'); if (Test-Path -LiteralPath $$marker) { $$task = Get-ScheduledTask -TaskName 'Reins WeCom Ticket Poller' -ErrorAction SilentlyContinue; if ($$null -ne $$task) { Enable-ScheduledTask -InputObject $$task -ErrorAction SilentlyContinue | Out-Null; Start-ScheduledTask -InputObject $$task -ErrorAction SilentlyContinue }; Remove-Item -LiteralPath $$marker -Force -ErrorAction SilentlyContinue } }"`
  Pop $0
!macroend

!macro REINS_STOP_RUNTIME_PROCESSES
  DetailPrint "Stopping Reins background processes..."

  ; The ticket poller runs the bundled Python continuously through Task
  ; Scheduler, even when the desktop window is closed. Disable it before
  ; stopping it so its automatic restart policy cannot race the installer.
  !insertmacro REINS_PAUSE_BACKGROUND_TASK

  ; Stop the desktop and command process trees before touching runtime DLLs.
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /F /T /IM "Reins.exe"'
  Pop $0
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /F /T /IM "reins-runtime.exe"'
  Pop $0
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /F /T /IM "officecli.exe"'
  Pop $0
  Sleep 500

  ; Catch orphaned private Node or Python processes by executable path. Keep
  ; this command below NSIS's 1024-character string limit; a longer command is
  ; silently truncated and reaches PowerShell as invalid syntax.
  nsExec::ExecToLog `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "& { $$r=[IO.Path]::GetFullPath((Join-Path $$env:LOCALAPPDATA 'Reins\runtime')).TrimEnd('\')+'\'; function q { @(Get-CimInstance Win32_Process -EA SilentlyContinue | ? { $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$r,[StringComparison]::OrdinalIgnoreCase) }) }; $$d=[DateTime]::UtcNow.AddSeconds(20); while ([DateTime]::UtcNow -lt $$d) { $$p=@(q); if (!$$p.Count) { exit 0 }; $$p | % { Stop-Process -Id $$_.ProcessId -Force -EA SilentlyContinue }; Start-Sleep -Milliseconds 500 }; $$p=@(q); if (!$$p.Count) { exit 0 }; $$p | % { Write-Output ('Still active: PID '+$$_.ProcessId+' '+$$_.ExecutablePath) }; exit 32 }"`
  Pop $0
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro REINS_STOP_RUNTIME_PROCESSES
  StrCmp $0 "0" reins_preinstall_runtime_stopped
  ; The poller was paused before the failed shutdown attempt. Restore its
  ; previous state when installation cannot continue.
  !insertmacro REINS_RESUME_BACKGROUND_TASK
  MessageBox MB_OK|MB_ICONSTOP "Reins could not stop its private runtime after 20 seconds. Close Reins and try this installer again. You do not need to uninstall Reins or restart Windows."
  Abort

  reins_preinstall_runtime_stopped:
  ; Reins 0.1.0 accidentally removed inherited permissions from its own
  ; current-user installation directory. Repair that directory before an
  ; upgrade copies the new application files.
  nsExec::ExecToLog '"$SYSDIR\icacls.exe" "$LOCALAPPDATA\Reins" /inheritance:e /reset /T /C'
  Pop $0
!macroend

!macro NSIS_HOOK_POSTINSTALL
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Reins" "ReinsUpgradeRecoveryVersion"
  ; Resume the poller only when it was enabled before this upgrade.
  !insertmacro REINS_RESUME_BACKGROUND_TASK
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro REINS_STOP_RUNTIME_PROCESSES
  ; Never make the uninstaller permanently unusable because a maintenance
  ; process could not be inspected. Continue cleanup and let NSIS schedule
  ; locked runtime directories for removal when Windows releases them.
  StrCmp $0 "0" +2 0
  DetailPrint "A Reins runtime process is still closing; uninstall cleanup will continue."
  nsExec::ExecToLog '"$SYSDIR\schtasks.exe" /Delete /TN "Reins WeCom Ticket Poller" /F'
  Pop $0
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; If Windows still has a late runtime handle, remove the private runtime as
  ; soon as that handle is released instead of leaving a half-installed copy.
  RMDir /r /REBOOTOK "$LOCALAPPDATA\Reins\runtime"
  RMDir /REBOOTOK "$LOCALAPPDATA\Reins"
!macroend
