!macro NSIS_HOOK_POSTINSTALL
  CreateDirectory "$LOCALAPPDATA\reins"
  CreateDirectory "$LOCALAPPDATA\reins\logs"
  ReadEnvStr $0 "USERNAME"
  nsExec::ExecToLog 'icacls.exe "$LOCALAPPDATA\reins" /inheritance:r /grant:r "$0:(OI)(CI)F" /T /C'
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::ExecToLog 'schtasks.exe /End /TN "Reins WeCom Ticket Poller"'
  nsExec::ExecToLog 'schtasks.exe /Delete /TN "Reins WeCom Ticket Poller" /F'
!macroend
