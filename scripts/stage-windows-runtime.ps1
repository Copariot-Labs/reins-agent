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

$WebLockfile = Join-Path $WebRoot "pnpm-lock.yaml"
if (-not (Test-Path $WebLockfile)) {
    throw "Required build input is missing: $WebLockfile. Commit the web lockfile before building the Windows installer."
}

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
    pnpm = @{
        onlyBuiltDependencies = @("node-pty")
    }
    dependencies = @{
        "node-pty" = [string]$SourcePackage.dependencies."node-pty"
        "socket.io" = [string]$SourcePackage.dependencies."socket.io"
    }
}
$RuntimePackage | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Runtime "web\package.json") -Encoding UTF8
Invoke-Checked $Pnpm @("install", "--prod", "--config.node-linker=hoisted") (Join-Path $Runtime "web")
$RuntimeNode = Join-Path $Runtime "node\node.exe"
Invoke-Checked $RuntimeNode @(
    "-e",
    "require('node-pty'); require('socket.io'); console.log('Private Reins JavaScript runtime verified')"
) (Join-Path $Runtime "web")
Invoke-Checked $RuntimeNode @("--check", "server\index.js") (Join-Path $Runtime "web")

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
    "pip", "install", "--python", $RuntimePython, "--system", "--break-system-packages",
    (Join-Path $ProjectRoot "vendor\hermes-agent"),
    $ProjectRoot
)
$RuntimeProbe = "import importlib.util; from reins.features.finance.db import get_migrations_dir; names=('hermes_cli','playwright','reins','run_agent'); missing=[name for name in names if importlib.util.find_spec(name) is None]; migrations=get_migrations_dir(); required=migrations/'001_init.sql'; assert not missing, f'Missing runtime modules: {missing}'; assert migrations.is_dir(), f'Missing Finance migrations directory: {migrations}'; assert required.is_file(), f'Missing Finance migration: {required}'; print('Private Reins Python runtime verified; Finance migrations verified')"
Invoke-Checked $RuntimePython @("-c", $RuntimeProbe)

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

Write-Host "==> Smoke testing the staged Reins local service" -ForegroundColor Cyan
$SmokeHome = Join-Path ([IO.Path]::GetTempPath()) "reins-runtime-smoke"
$SmokeStdout = Join-Path $SmokeHome "stdout.log"
$SmokeStderr = Join-Path $SmokeHome "stderr.log"
New-Item -ItemType Directory -Force -Path $SmokeHome | Out-Null
$SmokeEnvironment = @{
    PORT = "18648"
    BIND_HOST = "127.0.0.1"
    REINS_DESKTOP = "1"
    REINS_HOME = $SmokeHome
    HERMES_HOME = $SmokeHome
    HERMES_WEB_UI_HOME = (Join-Path $SmokeHome "web-ui")
    HERMES_WEB_UI_DISABLE_UPDATE_CHECK = "true"
    REINS_SKIP_BACKGROUND_SERVICES = "1"
}
$PreviousSmokeEnvironment = @{}
foreach ($Name in $SmokeEnvironment.Keys) {
    $PreviousSmokeEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
    [Environment]::SetEnvironmentVariable($Name, $SmokeEnvironment[$Name], "Process")
}
$SmokeProcess = $null
try {
    $SmokeProcess = Start-Process -FilePath $RuntimeNode `
        -ArgumentList @("server\index.js") `
        -WorkingDirectory (Join-Path $Runtime "web") `
        -WindowStyle Hidden `
        -RedirectStandardOutput $SmokeStdout `
        -RedirectStandardError $SmokeStderr `
        -PassThru
    $SmokeReady = $false
    $SmokeDeadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $SmokeDeadline -and -not $SmokeProcess.HasExited) {
        try {
            $Request = [Net.HttpWebRequest]::Create("http://127.0.0.1:18648/health/ready")
            $Request.Proxy = $null
            $Request.Timeout = 2000
            $Response = $Request.GetResponse()
            if ([int]$Response.StatusCode -eq 200) {
                $SmokeReady = $true
                $Response.Dispose()
                break
            }
            $Response.Dispose()
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $SmokeReady) {
        $Output = if (Test-Path $SmokeStdout) { Get-Content $SmokeStdout -Raw } else { "" }
        $Errors = if (Test-Path $SmokeStderr) { Get-Content $SmokeStderr -Raw } else { "" }
        throw "Staged Reins local service failed its readiness check.`n$Output`n$Errors"
    }
    Write-Host "Staged Reins local service verified" -ForegroundColor Green
}
finally {
    if ($null -ne $SmokeProcess -and -not $SmokeProcess.HasExited) {
        Stop-Process -Id $SmokeProcess.Id -Force -ErrorAction SilentlyContinue
        $SmokeProcess.WaitForExit(5000) | Out-Null
    }
    foreach ($Name in $SmokeEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousSmokeEnvironment[$Name], "Process")
    }
}

Write-Host "Reins private Windows runtime staged at $Runtime" -ForegroundColor Green
