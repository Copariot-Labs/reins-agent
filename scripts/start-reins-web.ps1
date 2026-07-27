$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ReinsRoot = Resolve-Path (Join-Path $ScriptDir "..")

Set-Location $ReinsRoot

$ActivateScript = Join-Path $ReinsRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    . $ActivateScript
}

reins web @args
exit $LASTEXITCODE
