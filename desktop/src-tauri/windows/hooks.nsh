!macro NSIS_HOOK_PREINSTALL
  ; Reins 0.1.0 accidentally removed inherited permissions from its own
  ; current-user installation directory. Repair that directory before an
  ; upgrade copies the new application files.
  nsExec::ExecToLog 'icacls.exe "$LOCALAPPDATA\Reins" /inheritance:e /reset /T /C'
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::ExecToLog 'schtasks.exe /End /TN "Reins WeCom Ticket Poller"'
  nsExec::ExecToLog 'schtasks.exe /Delete /TN "Reins WeCom Ticket Poller" /F'
!macroend
