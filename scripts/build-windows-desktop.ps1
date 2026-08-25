#Requires -Version 5.1

[CmdletBinding()]
param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc",
    [string]$AdministratorPasswordHash = $env:REINS_ADMIN_PASSWORD_HASH
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "The Reins Windows installer must be built on Windows."
}

$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$DesktopRoot = Join-Path $ProjectRoot "desktop"
$ReleaseDir = Join-Path $ProjectRoot "release"
$HashTool = Join-Path $ProjectRoot "scripts\generate-admin-password-hash.mjs"
$Node = (Get-Command "node.exe" -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source

function ConvertTo-PlainText {
    param([Parameter(Mandatory = $true)][Security.SecureString]$Value)
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer) }
}

function Invoke-AdminHashTool {
    param(
        [Parameter(Mandatory = $true)][string]$InputValue,
        [string[]]$Arguments = @()
    )
    $Output = $InputValue | & $Node $HashTool @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Administrator password configuration is invalid." }
    return (($Output | Out-String).Trim())
}

$PlainPassword = $null
try {
    if (-not $AdministratorPasswordHash) {
        $PlainPassword = $env:REINS_ADMIN_PASSWORD

        if (-not $PlainPassword) {
            if ($env:CI) {
                throw "Set the REINS_ADMIN_PASSWORD or REINS_ADMIN_PASSWORD_HASH secret before building the Windows installer."
            }

            $First = Read-Host "Enter the administrator password for this Windows build" -AsSecureString
            $Second = Read-Host "Confirm the administrator password" -AsSecureString
            $PlainPassword = ConvertTo-PlainText $First
            $Confirmation = ConvertTo-PlainText $Second
            if ($PlainPassword -cne $Confirmation) {
                throw "The administrator passwords do not match."
            }
            $Confirmation = $null
        }

        $AdministratorPasswordHash = Invoke-AdminHashTool $PlainPassword
    }
    else {
        Invoke-AdminHashTool -InputValue $AdministratorPasswordHash -Arguments @("--validate") | Out-Null
        $AdministratorPasswordHash = $AdministratorPasswordHash.Trim()
    }
}
finally {
    $PlainPassword = $null
    Remove-Item Env:REINS_ADMIN_PASSWORD -ErrorAction SilentlyContinue
}

$env:REINS_ADMIN_PASSWORD_HASH = $AdministratorPasswordHash

Push-Location $DesktopRoot
try {
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed" }
    pnpm tauri build --target $TargetTriple
    if ($LASTEXITCODE -ne 0) { throw "Tauri Windows build failed" }
}
finally { Pop-Location }

$BundleDir = Join-Path $DesktopRoot "src-tauri\target\$TargetTriple\release\bundle\nsis"
$Installer = Get-ChildItem $BundleDir -Filter "*-setup.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $Installer) { throw "Tauri did not produce an NSIS setup executable in $BundleDir" }

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$PublishedInstaller = Join-Path $ReleaseDir "Reins-Setup-x64.exe"
Copy-Item -Force $Installer.FullName $PublishedInstaller

Write-Host "Reins installer created:" -ForegroundColor Green
Write-Host $PublishedInstaller
