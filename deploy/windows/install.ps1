#Requires -Version 5.1

[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$SkipWeCom,
    [switch]$NoDesktop,
    [string]$ReinsHome,
    [string]$Workspace
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$WebTaskName = "Reins Web UI"
$WebUrl = "http://127.0.0.1:8648"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = [IO.Path]::GetFullPath((Join-Path $ScriptDir "..\.."))

function Write-Step {
    param([string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-WarningMessage {
    param([string]$Message)
    Write-Warning $Message
}

function Resolve-UserPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $expanded = [Environment]::ExpandEnvironmentVariables($Path.Trim())
    if ($expanded -eq "~") {
        $expanded = $env:USERPROFILE
    }
    elseif ($expanded.StartsWith("~\") -or $expanded.StartsWith("~/")) {
        $expanded = Join-Path $env:USERPROFILE $expanded.Substring(2)
    }
    if (-not [IO.Path]::IsPathRooted($expanded)) {
        $expanded = Join-Path (Get-Location).Path $expanded
    }
    return [IO.Path]::GetFullPath($expanded)
}

function Get-ApplicationPath {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $command) {
        throw "Required command was not found: $Name"
    }
    return $command.Source
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

function ConvertTo-PowerShellLiteral {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Write-Utf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Content,
        [switch]$WithBom
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temporary = "$Path.tmp.$PID"
    $encoding = New-Object System.Text.UTF8Encoding($WithBom.IsPresent)
    [IO.File]::WriteAllText($temporary, $Content, $encoding)
    Move-Item -Force -Path $temporary -Destination $Path
}

function Wait-ForWeb {
    param([int]$Attempts = 240)

    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "$WebUrl/health" -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return $true
            }
        }
        catch {
            # The service may still be starting.
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function New-WebRuntimeScript {
    param(
        [string]$Destination,
        [string]$NodePath,
        [string]$WebRoot,
        [string]$WebServer,
        [string]$PythonPath,
        [string]$ReinsExecutable,
        [string]$DataHome,
        [string]$WorkspacePath
    )

    $nodeArgument = '"' + $WebServer + '"'
    $lines = @(
        "#Requires -Version 5.1",
        "`$ErrorActionPreference = 'Stop'",
        "`$ProgressPreference = 'SilentlyContinue'",
        "`$env:NODE_ENV = 'production'",
        "`$env:PORT = '8648'",
        "`$env:BIND_HOST = '127.0.0.1'",
        "`$env:REINS_HOME = $(ConvertTo-PowerShellLiteral $DataHome)",
        "`$env:HERMES_HOME = $(ConvertTo-PowerShellLiteral $DataHome)",
        "`$env:HERMES_WEB_UI_HOME = $(ConvertTo-PowerShellLiteral (Join-Path $DataHome 'web-ui'))",
        "`$env:HERMES_AGENT_ROOT = $(ConvertTo-PowerShellLiteral (Join-Path $ProjectDir 'vendor\hermes-agent'))",
        "`$env:HERMES_AGENT_BRIDGE_PYTHON = $(ConvertTo-PowerShellLiteral $PythonPath)",
        "`$env:REINS_BIN = $(ConvertTo-PowerShellLiteral $ReinsExecutable)",
        "`$env:HERMES_BIN = $(ConvertTo-PowerShellLiteral $ReinsExecutable)",
        "`$env:WORKSPACE_BASE = $(ConvertTo-PowerShellLiteral $WorkspacePath)",
        "`$env:PYTHONIOENCODING = 'utf-8'",
        "`$env:PYTHONUTF8 = '1'",
        "`$env:PATH = $(ConvertTo-PowerShellLiteral ((Split-Path -Parent $PythonPath) + ';' + (Split-Path -Parent $NodePath) + ';')) + `$env:PATH",
        "`$logDirectory = $(ConvertTo-PowerShellLiteral (Join-Path $DataHome 'logs'))",
        "New-Item -ItemType Directory -Force -Path `$logDirectory | Out-Null",
        "`$stdoutPath = Join-Path `$logDirectory 'web-runtime.log'",
        "`$stderrPath = Join-Path `$logDirectory 'web-runtime.error.log'",
        "`$nodeArgument = $(ConvertTo-PowerShellLiteral $nodeArgument)",
        "`$process = Start-Process -FilePath $(ConvertTo-PowerShellLiteral $NodePath) -ArgumentList `$nodeArgument -WorkingDirectory $(ConvertTo-PowerShellLiteral $WebRoot) -NoNewWindow -Wait -PassThru -RedirectStandardOutput `$stdoutPath -RedirectStandardError `$stderrPath",
        "exit `$process.ExitCode",
        ""
    )
    Write-Utf8File -Path $Destination -Content ($lines -join "`r`n") -WithBom
}

function New-OpenScript {
    param([string]$Destination)

    $lines = @(
        "#Requires -Version 5.1",
        "`$ErrorActionPreference = 'Stop'",
        "`$ProgressPreference = 'SilentlyContinue'",
        "`$taskName = $(ConvertTo-PowerShellLiteral $WebTaskName)",
        "`$webUrl = $(ConvertTo-PowerShellLiteral $WebUrl)",
        "try {",
        "    `$task = Get-ScheduledTask -TaskName `$taskName -ErrorAction Stop",
        "    if (`$task.State -ne 'Running') {",
        "        Start-ScheduledTask -TaskName `$taskName",
        "    }",
        "    for (`$attempt = 0; `$attempt -lt 120; `$attempt++) {",
        "        try {",
        "            `$response = Invoke-WebRequest -UseBasicParsing -Uri `"`$webUrl/health`" -TimeoutSec 2",
        "            if (`$response.StatusCode -eq 200) {",
        "                Start-Process `$webUrl",
        "                exit 0",
        "            }",
        "        } catch {}",
        "        Start-Sleep -Milliseconds 500",
        "    }",
        "    throw 'Reins did not become ready within 60 seconds.'",
        "} catch {",
        "    `$message = `"Could not open Reins.`r`n`r`n`$(`$_.Exception.Message)`"",
        "    try {",
        "        Add-Type -AssemblyName PresentationFramework",
        "        [System.Windows.MessageBox]::Show(`$message, 'Reins', 'OK', 'Error') | Out-Null",
        "    } catch {",
        "        Write-Error `$message",
        "    }",
        "    exit 1",
        "}",
        ""
    )
    Write-Utf8File -Path $Destination -Content ($lines -join "`r`n") -WithBom
}

function New-Shortcut {
    param(
        [string]$Path,
        [string]$Target,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$IconPath
    )

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = "$IconPath,0"
    $shortcut.Description = "Open Reins"
    $shortcut.WindowStyle = 7
    $shortcut.Save()
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "This installer supports Windows only."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Do not run this installer as Administrator. Open a normal PowerShell window as the target desktop user."
}

$localAppData = $env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($localAppData)) {
    $localAppData = Join-Path $env:USERPROFILE "AppData\Local"
}
$StateDir = Join-Path $localAppData "reins-deploy"
$ReinsHomeState = Join-Path $StateDir "reins-home"
$WorkspaceState = Join-Path $StateDir "workspace"

if ([string]::IsNullOrWhiteSpace($ReinsHome)) {
    if (-not [string]::IsNullOrWhiteSpace($env:REINS_HOME)) {
        $ReinsHome = $env:REINS_HOME
    }
    elseif (Test-Path $ReinsHomeState) {
        $ReinsHome = [IO.File]::ReadAllText($ReinsHomeState).Trim()
    }
    else {
        $ReinsHome = Join-Path $localAppData "reins"
    }
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    if (-not [string]::IsNullOrWhiteSpace($env:REINS_WORKSPACE_BASE)) {
        $Workspace = $env:REINS_WORKSPACE_BASE
    }
    elseif (Test-Path $WorkspaceState) {
        $Workspace = [IO.File]::ReadAllText($WorkspaceState).Trim()
    }
    else {
        $Workspace = Join-Path $env:USERPROFILE "Documents\Reins"
    }
}

$ReinsHome = Resolve-UserPath $ReinsHome
$Workspace = Resolve-UserPath $Workspace
$VenvDir = Join-Path $ProjectDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$ReinsExe = Join-Path $VenvDir "Scripts\reins.exe"
$WebRoot = Join-Path $ProjectDir "web"
$WebServer = Join-Path $WebRoot "dist\server\index.js"
$WebClient = Join-Path $WebRoot "dist\client\index.html"
$WebIcon = Join-Path $WebRoot "packages\client\public\favicon.ico"
$RuntimeScript = Join-Path $StateDir "reins-web-runtime.ps1"
$OpenScript = Join-Path $StateDir "reins-open.ps1"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $PowerShellExe)) {
    $PowerShellExe = Get-ApplicationPath "powershell.exe"
}

Write-Step "Preparing Reins directories"
@($StateDir, $ReinsHome, (Join-Path $ReinsHome "logs"), (Join-Path $ReinsHome "web-ui"), $Workspace) |
    ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
Write-Utf8File -Path $ReinsHomeState -Content $ReinsHome
Write-Utf8File -Path $WorkspaceState -Content $Workspace

$EnvFile = Join-Path $ReinsHome ".env"
if (-not (Test-Path $EnvFile)) {
    if (-not $SkipWeCom) {
        throw "Missing $EnvFile. Configure it first, or rerun with -SkipWeCom."
    }
    Write-WarningMessage "$EnvFile does not exist; model and provider setup must be completed in Reins."
}

$NodeExe = Get-ApplicationPath "node.exe"
$NodeMajor = & $NodeExe -p "Number(process.versions.node.split('.')[0])"
if ($LASTEXITCODE -ne 0 -or -not ($NodeMajor -as [int])) {
    throw "Could not determine the Node.js version."
}
if ([int]$NodeMajor -lt 23) {
    throw "Node.js 23 or newer is required; found $(& $NodeExe --version)."
}

if (-not $SkipBuild) {
    $UvExe = Get-ApplicationPath "uv.exe"
    $NpmExe = Get-ApplicationPath "npm.cmd"

    if (-not (Test-Path (Join-Path $ProjectDir "vendor\hermes-agent\run_agent.py"))) {
        $GitExe = Get-ApplicationPath "git.exe"
        Write-Step "Initializing Git submodules"
        Invoke-NativeCommand $GitExe @("-C", $ProjectDir, "submodule", "update", "--init", "--recursive")
    }
    if (-not (Test-Path (Join-Path $ProjectDir "vendor\hermes-agent\run_agent.py"))) {
        throw "The Hermes submodule is incomplete: $(Join-Path $ProjectDir 'vendor\hermes-agent')"
    }

    $VenvIsValid = $false
    if (Test-Path $PythonExe) {
        & $PythonExe -c "import sys; raise SystemExit(0 if sys.platform == 'win32' and sys.version_info >= (3, 11) else 1)" 2>$null
        $VenvIsValid = $LASTEXITCODE -eq 0
    }
    if (-not $VenvIsValid) {
        Write-Step "Creating a Windows Python virtual environment"
        Push-Location $ProjectDir
        try {
            Invoke-NativeCommand $UvExe @("venv", "--clear", $VenvDir)
        }
        finally {
            Pop-Location
        }
    }
    if (-not (Test-Path $PythonExe)) {
        throw "The Windows virtual environment was not created: $PythonExe"
    }
    Invoke-NativeCommand $PythonExe @("-c", "import sys; raise SystemExit(0 if sys.platform == 'win32' and sys.version_info >= (3, 11) else 1)")

    Write-Step "Installing Python packages"
    Invoke-NativeCommand $UvExe @("pip", "install", "--python", $PythonExe, "-e", (Join-Path $ProjectDir "vendor\hermes-agent"))
    Invoke-NativeCommand $UvExe @("pip", "install", "--python", $PythonExe, "-e", $ProjectDir)

    Write-Step "Building the production Web UI"
    Push-Location $WebRoot
    try {
        Invoke-NativeCommand $NpmExe @("ci")
        Invoke-NativeCommand $NpmExe @("run", "build")
    }
    finally {
        Pop-Location
    }
}

@($PythonExe, $ReinsExe, $WebServer, $WebClient, $WebIcon) | ForEach-Object {
    if (-not (Test-Path $_)) {
        throw "Required deployment file was not found: $_"
    }
}

$env:REINS_HOME = $ReinsHome
$env:HERMES_HOME = $ReinsHome
$env:REINS_SERVICE_PYTHON = $PythonExe
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
Invoke-NativeCommand $PythonExe @("-c", "import reins.main")

if (-not $SkipWeCom) {
    Write-Step "Validating WeCom and enabling its plugin"
    Invoke-NativeCommand $ReinsExe @("wecom", "ticket-api", "doctor", "--json")
    Invoke-NativeCommand $ReinsExe @("wecom", "install-plugin")
    Invoke-NativeCommand $ReinsExe @("plugins", "enable", "reins-wecom", "--no-allow-tool-override")
}

Write-Step "Installing the production Web UI task"
New-WebRuntimeScript -Destination $RuntimeScript -NodePath $NodeExe -WebRoot $WebRoot -WebServer $WebServer -PythonPath $PythonExe -ReinsExecutable $ReinsExe -DataHome $ReinsHome -WorkspacePath $Workspace
New-OpenScript -Destination $OpenScript

$existingTask = Get-ScheduledTask -TaskName $WebTaskName -ErrorAction SilentlyContinue
if ($null -ne $existingTask -and $existingTask.State -eq "Running") {
    Stop-ScheduledTask -TaskName $WebTaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

$UserId = $identity.Name
$ActionArguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $RuntimeScript
$Action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument $ActionArguments -WorkingDirectory $WebRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$TaskPrincipal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $WebTaskName -Action $Action -Trigger $Trigger -Principal $TaskPrincipal -Settings $Settings -Description "Reins production Web UI" -Force | Out-Null
Start-ScheduledTask -TaskName $WebTaskName

if (-not (Wait-ForWeb)) {
    $task = Get-ScheduledTask -TaskName $WebTaskName -ErrorAction SilentlyContinue
    $taskState = if ($null -eq $task) { "missing" } else { [string]$task.State }
    throw "Reins Web UI did not become healthy. Task state: $taskState. Check $ReinsHome\logs\web-runtime.error.log"
}

if (-not $SkipWeCom) {
    Write-Step "Installing the WeCom ticket poller task"
    Invoke-NativeCommand $ReinsExe @("wecom", "ticket-api", "service", "install")
    Invoke-NativeCommand $ReinsExe @("wecom", "ticket-api", "service", "status")
}

if (-not $NoDesktop) {
    Write-Step "Creating Desktop and Start Menu shortcuts"
    $ShortcutArguments = '-NoLogo -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $OpenScript
    $DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Reins.lnk"
    $StartMenuShortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "Reins.lnk"
    New-Shortcut -Path $DesktopShortcut -Target $PowerShellExe -Arguments $ShortcutArguments -WorkingDirectory $ProjectDir -IconPath $WebIcon
    New-Shortcut -Path $StartMenuShortcut -Target $PowerShellExe -Arguments $ShortcutArguments -WorkingDirectory $ProjectDir -IconPath $WebIcon
}

Write-Host "`nReins is installed for $UserId." -ForegroundColor Green
Write-Host "Web UI:       $WebUrl"
Write-Host "Data:         $ReinsHome"
Write-Host "Workspace:    $Workspace"
Write-Host "Web task:     $WebTaskName"
Write-Host "Update later: git pull, then .\deploy\windows\install.ps1"
