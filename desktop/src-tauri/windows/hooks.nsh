!macro REINS_STOP_RUNTIME_PROCESSES
  DetailPrint "Stopping Reins background processes..."

  ; The ticket poller runs the bundled Python continuously through Task
  ; Scheduler, even when the desktop window is closed. End it before touching
  ; runtime DLLs, then stop the desktop and command process trees.
  nsExec::ExecToLog '"$SYSDIR\schtasks.exe" /End /TN "Reins WeCom Ticket Poller"'
  Pop $0
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /F /T /IM "Reins.exe"'
  Pop $0
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /F /T /IM "reins-runtime.exe"'
  Pop $0
  nsExec::ExecToLog '"$SYSDIR\taskkill.exe" /F /T /IM "officecli.exe"'
  Pop $0
  Sleep 750

  ; Catch an orphaned private node.exe or python.exe by executable path. Never
  ; terminate unrelated Node or Python processes belonging to other software.
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "& { $$root = [IO.Path]::GetFullPath((Join-Path $$env:LOCALAPPDATA Reins)); $$prefix = $$root + [IO.Path]::DirectorySeparatorChar; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $$_.ExecutablePath -and $$_.ExecutablePath.StartsWith($$prefix, [StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $$_.ProcessId -Force -ErrorAction SilentlyContinue } }"'
  Pop $0
  Sleep 1250
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro REINS_STOP_RUNTIME_PROCESSES

  ; Reins 0.1.0 accidentally removed inherited permissions from its own
  ; current-user installation directory. Repair that directory before an
  ; upgrade copies the new application files.
  nsExec::ExecToLog '"$SYSDIR\icacls.exe" "$LOCALAPPDATA\Reins" /inheritance:e /reset /T /C'
  Pop $0
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro REINS_STOP_RUNTIME_PROCESSES
  nsExec::ExecToLog '"$SYSDIR\schtasks.exe" /Delete /TN "Reins WeCom Ticket Poller" /F'
  Pop $0
!macroend
