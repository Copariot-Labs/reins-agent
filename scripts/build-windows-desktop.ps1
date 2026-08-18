#Requires -Version 5.1

[CmdletBinding()]
param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "The Reins Windows installer must be built on Windows."
}

$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$DesktopRoot = Join-Path $ProjectRoot "desktop"
$ReleaseDir = Join-Path $ProjectRoot "release"

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
