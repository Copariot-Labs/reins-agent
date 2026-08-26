#Requires -Version 5.1

[CmdletBinding()]
param(
    [string]$Installer = "release\Reins-Setup-x64.exe",
    [int]$TimeoutSeconds = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "The Reins installer smoke test must run on Windows."
}

$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$InstallerPath = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Installer))
$InstallRoot = Join-Path $env:LOCALAPPDATA "Reins"
$RuntimeRoot = Join-Path $InstallRoot "runtime"
$AppPath = Join-Path $InstallRoot "Reins.exe"
$UninstallerPath = Join-Path $InstallRoot "uninstall.exe"

if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    throw "Reins installer not found: $InstallerPath"
}

function Invoke-CheckedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$Label
    )

    Write-Host "==> $Label" -ForegroundColor Cyan
    $Process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru
    if (-not $Process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw "$Label timed out after $TimeoutSeconds seconds."
    }
    if ($Process.ExitCode -ne 0) {
        throw "$Label failed with exit code $($Process.ExitCode)."
    }
}

function Get-ReinsRuntimeProcesses {
    if (-not (Test-Path -LiteralPath $RuntimeRoot -PathType Container)) {
        return @()
    }

    $Prefix = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd(
        [IO.Path]::DirectorySeparatorChar
    ) + [IO.Path]::DirectorySeparatorChar

    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ExecutablePath -and
                $_.ExecutablePath.StartsWith(
                    $Prefix,
                    [StringComparison]::OrdinalIgnoreCase
                )
            }
    )
}

function Stop-ReinsSmokeProcesses {
    try {
        & "$env:SystemRoot\System32\taskkill.exe" /F /T /IM "Reins.exe" `
            2>$null | Out-Null
    }
    catch {
        # taskkill returns a non-zero status when Reins is already stopped.
    }
    Get-ReinsRuntimeProcesses | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Assert-ReinsInstalled {
    foreach ($RequiredFile in @(
        $AppPath,
        $UninstallerPath,
        (Join-Path $RuntimeRoot "python\DLLs\_asyncio.pyd"),
        (Join-Path $RuntimeRoot "bin\reins-runtime.exe")
    )) {
        if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
            throw "Installed Reins file is missing: $RequiredFile"
        }
    }
}

function Invoke-ReinsUninstallCheck {
    param([Parameter(Mandatory = $true)][string]$Label)

    Invoke-CheckedProcess -FilePath $UninstallerPath -Arguments @("/S") `
        -Label $Label

    $RemovalDeadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $RemainingInstalledFiles = @(
            @($AppPath, $UninstallerPath) |
                Where-Object { Test-Path -LiteralPath $_ }
        )
        if ($RemainingInstalledFiles.Count -eq 0) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $RemovalDeadline)

    foreach ($RemovedFile in $RemainingInstalledFiles) {
        throw "Reins uninstall left an installed executable behind: $RemovedFile"
    }
}

try {
    if ((Test-Path -LiteralPath $AppPath) -or
        (Test-Path -LiteralPath $UninstallerPath)) {
        throw "The Windows release runner is not clean: $InstallRoot"
    }

    Invoke-CheckedProcess -FilePath $InstallerPath -Arguments @("/S", "/NS") `
        -Label "Installing Reins into a clean current-user location"

    Assert-ReinsInstalled

    Write-Host "==> Starting Reins to lock its private runtime" -ForegroundColor Cyan
    $App = Start-Process -FilePath $AppPath -PassThru
    $RuntimeDeadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 500
        $RuntimeProcesses = @(Get-ReinsRuntimeProcesses)
    } while ($RuntimeProcesses.Count -eq 0 -and [DateTime]::UtcNow -lt $RuntimeDeadline)

    if ($RuntimeProcesses.Count -eq 0) {
        throw "Reins did not start a bundled runtime process for the upgrade smoke test."
    }

    Invoke-CheckedProcess -FilePath $InstallerPath `
        -Arguments @("/S", "/NS", "/UPDATE") `
        -Label "Reinstalling Reins while its desktop runtime is active"

    Start-Sleep -Seconds 2
    $RuntimeProcesses = @(Get-ReinsRuntimeProcesses)
    if ($RuntimeProcesses.Count -ne 0) {
        $Details = ($RuntimeProcesses | ForEach-Object {
            "PID $($_.ProcessId): $($_.ExecutablePath)"
        }) -join "; "
        throw "Reins runtime processes survived the upgrade: $Details"
    }

    if (-not (Test-Path -LiteralPath $UninstallerPath -PathType Leaf)) {
        throw "The upgraded Reins uninstaller is missing."
    }

    Invoke-ReinsUninstallCheck -Label "Uninstalling the upgraded Reins release"

    Invoke-CheckedProcess -FilePath $InstallerPath -Arguments @("/S", "/NS") `
        -Label "Reinstalling Reins after Windows uninstallation"
    Assert-ReinsInstalled

    Invoke-ReinsUninstallCheck -Label "Uninstalling the clean reinstallation"

    Write-Host "Reins clean install, active-runtime upgrade, uninstall, and reinstall checks passed." `
        -ForegroundColor Green
}
finally {
    Stop-ReinsSmokeProcesses
}
