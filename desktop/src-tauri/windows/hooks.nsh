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

  ; Catch orphaned private node.exe or python.exe processes by executable path.
  ; Repeat until the runtime is fully drained because a terminating parent can
  ; briefly leave children behind. Never terminate unrelated Node or Python
  ; processes belonging to other software.
  nsExec::ExecToLog `"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "& { $$root = [IO.Path]::GetFullPath((Join-Path $$env:LOCALAPPDATA Reins)); $$prefix = $$root.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar; $$deadline = [DateTime]::UtcNow.AddSeconds(20); do { $$processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$prefix, [StringComparison]::OrdinalIgnoreCase) }); if ($$processes.Count -eq 0) { Start-Sleep -Milliseconds 750; $$processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$prefix, [StringComparison]::OrdinalIgnoreCase) }); if ($$processes.Count -eq 0) { exit 0 } }; $$processes | ForEach-Object { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 500 } while ([DateTime]::UtcNow -lt $$deadline); $$remaining = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$prefix, [StringComparison]::OrdinalIgnoreCase) }); if ($$remaining.Count -eq 0) { exit 0 }; $$marker = [IO.Path]::Combine('$PLUGINSDIR', 'reins-poller-was-enabled'); if (Test-Path -LiteralPath $$marker) { $$task = Get-ScheduledTask -TaskName 'Reins WeCom Ticket Poller' -ErrorAction SilentlyContinue; if ($$null -ne $$task) { Enable-ScheduledTask -InputObject $$task -ErrorAction SilentlyContinue | Out-Null; Start-ScheduledTask -InputObject $$task -ErrorAction SilentlyContinue } }; Write-Error 'Reins runtime processes are still active.'; exit 32 }"`
  Pop $0
  StrCmp $0 "0" +3 0
  MessageBox MB_OK|MB_ICONSTOP "Reins could not stop its background service after 20 seconds. Close Reins and run this installer again. You do not need to uninstall Reins or restart Windows."
  Abort
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro REINS_STOP_RUNTIME_PROCESSES

  ; Reins 0.1.0 accidentally removed inherited permissions from its own
  ; current-user installation directory. Repair that directory before an
  ; upgrade copies the new application files.
  nsExec::ExecToLog '"$SYSDIR\icacls.exe" "$LOCALAPPDATA\Reins" /inheritance:e /reset /T /C'
  Pop $0
!macroend

!macro NSIS_HOOK_POSTINSTALL
  ; Resume the poller only when it was enabled before this upgrade.
  !insertmacro REINS_RESUME_BACKGROUND_TASK
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro REINS_STOP_RUNTIME_PROCESSES
  nsExec::ExecToLog '"$SYSDIR\schtasks.exe" /Delete /TN "Reins WeCom Ticket Poller" /F'
  Pop $0
!macroend
