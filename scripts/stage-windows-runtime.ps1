#Requires -Version 5.1

[CmdletBinding()]
param(
    [string]$PythonVersion = "3.12",
    [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "The Reins Windows runtime must be staged on Windows."
}

$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Runtime = Join-Path $ProjectRoot "desktop\src-tauri\runtime"
$WebRoot = Join-Path $ProjectRoot "web"
$PythonStore = Join-Path $ProjectRoot "desktop\.runtime-python"
$LauncherManifest = Join-Path $ProjectRoot "desktop\runtime-launcher\Cargo.toml"

function Invoke-Checked {
    param([Parameter(Mandatory = $true)][string]$FilePath, [string[]]$Arguments = @(), [string]$WorkingDirectory = $ProjectRoot)
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$FilePath exited with code $LASTEXITCODE" }
    }
    finally { Pop-Location }
}

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { throw "Required build command was not found: $Name" }
    return $command.Source
}

$Uv = Require-Command "uv.exe"
$Pnpm = Require-Command "pnpm.cmd"
$Cargo = Require-Command "cargo.exe"
$Dotnet = Require-Command "dotnet.exe"
$Node = Require-Command "node.exe"

Write-Host "==> Building the Reins web application" -ForegroundColor Cyan
Invoke-Checked $Pnpm @("install", "--frozen-lockfile") $WebRoot
Invoke-Checked $Pnpm @("build") $WebRoot

Write-Host "==> Creating the private Reins runtime" -ForegroundColor Cyan
if (Test-Path $Runtime) { Remove-Item -Recurse -Force $Runtime }
@(
    $Runtime,
    (Join-Path $Runtime "bin"),
    (Join-Path $Runtime "node"),
    (Join-Path $Runtime "web"),
    (Join-Path $Runtime "licenses")
) | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }

Copy-Item $Node (Join-Path $Runtime "node\node.exe")
$NodeLicense = Join-Path (Split-Path -Parent $Node) "LICENSE"
if (Test-Path $NodeLicense) {
    Copy-Item $NodeLicense (Join-Path $Runtime "licenses\javascript-runtime.txt")
}
Copy-Item -Recurse (Join-Path $WebRoot "dist\server") (Join-Path $Runtime "web\server")
Copy-Item -Recurse (Join-Path $WebRoot "dist\client") (Join-Path $Runtime "web\client")
Copy-Item -Recurse (Join-Path $WebRoot "dist\skills") (Join-Path $Runtime "web\skills")
$SourcePackage = Get-Content (Join-Path $WebRoot "package.json") -Raw | ConvertFrom-Json
$RuntimePackage = @{
    name = "reins-private-web-runtime"
    version = [string]$SourcePackage.version
    private = $true
    dependencies = @{
        "node-pty" = [string]$SourcePackage.dependencies."node-pty"
        "socket.io" = [string]$SourcePackage.dependencies."socket.io"
    }
}
$RuntimePackage | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Runtime "web\package.json") -Encoding UTF8
Invoke-Checked $Pnpm @("install", "--prod", "--config.node-linker=hoisted") (Join-Path $Runtime "web")

Write-Host "==> Installing the private Python runtime" -ForegroundColor Cyan
if (Test-Path $PythonStore) { Remove-Item -Recurse -Force $PythonStore }
New-Item -ItemType Directory -Force -Path $PythonStore | Out-Null
$PreviousUvInstallDir = $env:UV_PYTHON_INSTALL_DIR
$env:UV_PYTHON_INSTALL_DIR = $PythonStore
try {
    Invoke-Checked $Uv @("python", "install", $PythonVersion)
    $ManagedPython = (& $Uv python find --python-preference only-managed $PythonVersion).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ManagedPython)) {
        throw "uv did not create a private Python $PythonVersion runtime"
    }
}
finally {
    if ($null -eq $PreviousUvInstallDir) { Remove-Item Env:UV_PYTHON_INSTALL_DIR -ErrorAction SilentlyContinue }
    else { $env:UV_PYTHON_INSTALL_DIR = $PreviousUvInstallDir }
}

$ManagedPythonRoot = Split-Path -Parent $ManagedPython
$RuntimePythonRoot = Join-Path $Runtime "python"
New-Item -ItemType Directory -Force -Path $RuntimePythonRoot | Out-Null
Copy-Item -Recurse (Join-Path $ManagedPythonRoot "*") $RuntimePythonRoot
$RuntimePython = Join-Path $Runtime "python\python.exe"
if (-not (Test-Path $RuntimePython)) {
    throw "The private Python runtime was not staged at $RuntimePython"
}
Invoke-Checked $Uv @(
    "pip", "install", "--python", $RuntimePython, "--system",
    (Join-Path $ProjectRoot "vendor\hermes-agent"),
    $ProjectRoot
)

$PlaywrightBrowsers = Join-Path $Runtime "playwright"
$PreviousPlaywrightPath = $env:PLAYWRIGHT_BROWSERS_PATH
$env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsers
try { Invoke-Checked $RuntimePython @("-m", "playwright", "install", "chromium") }
finally {
    if ($null -eq $PreviousPlaywrightPath) { Remove-Item Env:PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue }
    else { $env:PLAYWRIGHT_BROWSERS_PATH = $PreviousPlaywrightPath }
}

Write-Host "==> Bundling the Reins agent engine" -ForegroundColor Cyan
$AgentTarget = Join-Path $Runtime "agent"
New-Item -ItemType Directory -Force -Path $AgentTarget | Out-Null
robocopy (Join-Path $ProjectRoot "vendor\hermes-agent") $AgentTarget /E /XD .git .venv venv __pycache__ tests /XF *.pyc *.pyo | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Could not stage the Reins agent engine (robocopy $LASTEXITCODE)" }

Write-Host "==> Building Reins Office support" -ForegroundColor Cyan
$OfficeOutput = Join-Path $ProjectRoot "desktop\.officecli-win-x64"
if (Test-Path $OfficeOutput) { Remove-Item -Recurse -Force $OfficeOutput }
Invoke-Checked $Dotnet @(
    "publish",
    (Join-Path $ProjectRoot "vendor\OfficeCLI\src\officecli\officecli.csproj"),
    "-c", "Release", "-r", "win-x64", "-o", $OfficeOutput,
    "--nologo", "-v", "minimal"
)
$OfficeExe = Join-Path $OfficeOutput "officecli.exe"
if (-not (Test-Path $OfficeExe)) { throw "Office support executable was not produced" }
Copy-Item $OfficeExe (Join-Path $Runtime "bin\officecli.exe")

Write-Host "==> Building the private Reins command launcher" -ForegroundColor Cyan
Invoke-Checked $Cargo @("build", "--manifest-path", $LauncherManifest, "--release", "--target", $TargetTriple)
$Launcher = Join-Path $ProjectRoot "desktop\runtime-launcher\target\$TargetTriple\release\reins-runtime.exe"
if (-not (Test-Path $Launcher)) { throw "Reins runtime launcher was not produced" }
Copy-Item $Launcher (Join-Path $Runtime "bin\reins-runtime.exe")

Copy-Item (Join-Path $ProjectRoot "vendor\hermes-agent\LICENSE") (Join-Path $Runtime "licenses\agent-runtime.txt")
Copy-Item (Join-Path $ProjectRoot "vendor\OfficeCLI\LICENSE") (Join-Path $Runtime "licenses\office-runtime.txt")
Copy-Item (Join-Path $ProjectRoot "vendor\OfficeCLI\NOTICE") (Join-Path $Runtime "licenses\office-notice.txt")
Copy-Item (Join-Path $ProjectRoot "vendor\OfficeCLI\THIRD-PARTY-NOTICES.txt") (Join-Path $Runtime "licenses\office-third-party-notices.txt")

Write-Host "Reins private Windows runtime staged at $Runtime" -ForegroundColor Green
