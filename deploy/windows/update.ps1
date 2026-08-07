#Requires -Version 5.1

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$WebTaskName = "Reins Web UI"
$WeComTaskName = "Reins WeCom Ticket Poller"
$localAppData = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = Join-Path $env:USERPROFILE "AppData\Local"
}

$StateDir = Join-Path $localAppData "reins-deploy"
$ProjectState = Join-Path $StateDir "project-root"
$ReinsHomeState = Join-Path $StateDir "reins-home"
$WorkspaceState = Join-Path $StateDir "workspace"
$InstallWeComState = Join-Path $StateDir "install-wecom"
$InstallDesktopState = Join-Path $StateDir "install-desktop"

function Read-StateValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Fallback
    )

    if (Test-Path $Path) {
        $value = [IO.File]::ReadAllText($Path).Trim()
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }
    return $Fallback
}

$ProjectDir = Read-StateValue -Path $ProjectState -Fallback ""
$ReinsHome = Read-StateValue -Path $ReinsHomeState -Fallback (Join-Path $localAppData "reins")
$Workspace = Read-StateValue -Path $WorkspaceState -Fallback (Join-Path $env:USERPROFILE "Documents\Reins")
$InstallWeCom = (Read-StateValue -Path $InstallWeComState -Fallback "1") -eq "1"
$InstallDesktop = (Read-StateValue -Path $InstallDesktopState -Fallback "1") -eq "1"
$LogDir = Join-Path $ReinsHome "logs"
$LogFile = Join-Path $LogDir "update.log"
$StatusFile = Join-Path $LogDir "update-status.json"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-UpdateStatus {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Message
    )

    $payload = [ordered]@{
        status = $Status
        message = $Message
        updated_at = [DateTime]::UtcNow.ToString("o")
    } | ConvertTo-Json -Compress
    $temporary = "$StatusFile.tmp.$PID"
    [IO.File]::WriteAllText($temporary, $payload, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -Force -Path $temporary -Destination $StatusFile
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgumentList = @()
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exited with code $LASTEXITCODE"
    }
}

function Stop-ReinsTask {
    param([Parameter(Mandatory = $true)][string]$TaskName)

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task -or $task.State -ne "Running") {
        return $false
    }

    Stop-ScheduledTask -TaskName $TaskName
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -eq $task -or $task.State -ne "Running") {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Scheduled task did not stop: $TaskName"
}

function Show-UpdateFailure {
    param([string]$Message)

    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show($Message, "Reins Update", "OK", "Error") | Out-Null
    }
    catch {
        # The update log remains available if the desktop cannot show a dialog.
    }
}

$mutex = New-Object Threading.Mutex($false, "Local\ReinsUpdate-$($env:USERNAME)")
if (-not $mutex.WaitOne(0)) {
    Write-UpdateStatus -Status "failed" -Message "Another Reins update is already running."
    exit 1
}

$transcriptStarted = $false
$webWasRunning = $false
$weComWasRunning = $false

try {
    Start-Transcript -Path $LogFile -Append | Out-Null
    $transcriptStarted = $true
    Write-UpdateStatus -Status "running" -Message "Downloading and installing the latest Reins version."
    Write-Host "`n[$([DateTime]::Now.ToString('s'))] Starting Reins update"

    if ([string]::IsNullOrWhiteSpace($ProjectDir)) {
        throw "The installed project path is missing."
    }
    if (-not (Test-Path (Join-Path $ProjectDir ".git"))) {
        throw "The installed Reins directory is not a Git checkout: $ProjectDir"
    }

    $Installer = Join-Path $ProjectDir "deploy\windows\install.ps1"
    if (-not (Test-Path $Installer)) {
        throw "The Windows installer is missing: $Installer"
    }

    $GitExe = (Get-Command "git.exe" -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

    # Give the Web request enough time to return before its task is stopped.
    Start-Sleep -Seconds 3
    $webWasRunning = Stop-ReinsTask -TaskName $WebTaskName
    $weComWasRunning = Stop-ReinsTask -TaskName $WeComTaskName

    Invoke-NativeCommand $GitExe @("-C", $ProjectDir, "pull", "--ff-only")

    $installParameters = @{
        ReinsHome = $ReinsHome
        Workspace = $Workspace
    }
    if (-not $InstallWeCom) {
        $installParameters.SkipWeCom = $true
    }
    if (-not $InstallDesktop) {
        $installParameters.NoDesktop = $true
    }

    & $Installer @installParameters

    if (-not $InstallWeCom -and $weComWasRunning) {
        Start-ScheduledTask -TaskName $WeComTaskName
    }

    Write-UpdateStatus -Status "success" -Message "Reins was updated successfully."
    Write-Host "[$([DateTime]::Now.ToString('s'))] Reins update completed" -ForegroundColor Green
}
catch {
    $failure = $_.Exception.Message
    Write-Host $failure -ForegroundColor Red
    Write-UpdateStatus -Status "failed" -Message "The update failed. See the Reins update log for details."

    if ($webWasRunning) {
        Start-ScheduledTask -TaskName $WebTaskName -ErrorAction SilentlyContinue
    }
    if ($weComWasRunning) {
        Start-ScheduledTask -TaskName $WeComTaskName -ErrorAction SilentlyContinue
    }

    Show-UpdateFailure -Message "Reins could not be updated.`r`n`r`n$failure`r`n`r`nLog: $LogFile"
    exit 1
}
finally {
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
