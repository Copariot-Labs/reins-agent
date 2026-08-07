#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$KeepWeCom
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$WebTaskName = "Reins Web UI"
$WeComTaskName = "Reins WeCom Ticket Poller"
$UpdateTaskName = "Reins Updater"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = [IO.Path]::GetFullPath((Join-Path $ScriptDir "..\.."))

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This uninstaller supports Windows only."
}

$localAppData = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = Join-Path $env:USERPROFILE "AppData\Local"
}
$StateDir = Join-Path $localAppData "reins-deploy"
$ReinsHomeState = Join-Path $StateDir "reins-home"
$ReinsHome = Join-Path $localAppData "reins"
if (Test-Path $ReinsHomeState) {
    $rememberedHome = [IO.File]::ReadAllText($ReinsHomeState).Trim()
    if (-not [string]::IsNullOrWhiteSpace($rememberedHome)) {
        $ReinsHome = $rememberedHome
    }
}

Write-Host "`n==> Removing the Reins Web UI task" -ForegroundColor Cyan
$webTask = Get-ScheduledTask -TaskName $WebTaskName -ErrorAction SilentlyContinue
if ($null -ne $webTask) {
    if ($webTask.State -eq "Running") {
        Stop-ScheduledTask -TaskName $WebTaskName -ErrorAction SilentlyContinue
    }
    Unregister-ScheduledTask -TaskName $WebTaskName -Confirm:$false
}

if (-not $KeepWeCom) {
    Write-Host "`n==> Removing the WeCom ticket poller task" -ForegroundColor Cyan
    $ReinsExe = Join-Path $ProjectDir ".venv\Scripts\reins.exe"
    $PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    $removedByCli = $false
    if (Test-Path $ReinsExe) {
        $env:REINS_HOME = $ReinsHome
        $env:HERMES_HOME = $ReinsHome
        $env:REINS_SERVICE_PYTHON = $PythonExe
        & $ReinsExe wecom ticket-api service uninstall
        $removedByCli = $LASTEXITCODE -eq 0
    }
    if (-not $removedByCli) {
        $weComTask = Get-ScheduledTask -TaskName $WeComTaskName -ErrorAction SilentlyContinue
        if ($null -ne $weComTask) {
            if ($weComTask.State -eq "Running") {
                Stop-ScheduledTask -TaskName $WeComTaskName -ErrorAction SilentlyContinue
            }
            Unregister-ScheduledTask -TaskName $WeComTaskName -Confirm:$false
        }
    }
}

Write-Host "`n==> Removing Reins shortcuts" -ForegroundColor Cyan
@(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Reins.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Programs")) "Reins.lnk")
) | ForEach-Object {
    if (Test-Path $_) {
        Remove-Item -Force -Path $_
    }
}

$updateTask = Get-ScheduledTask -TaskName $UpdateTaskName -ErrorAction SilentlyContinue
if ($null -ne $updateTask) {
    if ($updateTask.State -eq "Running") {
        Stop-ScheduledTask -TaskName $UpdateTaskName -ErrorAction SilentlyContinue
    }
    Unregister-ScheduledTask -TaskName $UpdateTaskName -Confirm:$false
}

if (Test-Path $StateDir) {
    Remove-Item -Recurse -Force -Path $StateDir
}

Write-Host "`nReins startup tasks and shortcuts were removed." -ForegroundColor Green
Write-Host "Application code and data were preserved."
Write-Host "Data: $ReinsHome"
