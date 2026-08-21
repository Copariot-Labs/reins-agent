from __future__ import annotations

import os
from pathlib import Path
import plistlib
import re
import shlex
import subprocess
import sys
from typing import Any, Sequence

from reins.api.home import get_reins_home
from reins.compat.bootstrap import get_project_root


SERVICE_LABEL = "ai.reins.wecom-ticket-poller"
WINDOWS_TASK_NAME = "Reins WeCom Ticket Poller"
SYSTEMD_UNIT_NAME = "reins-wecom-ticket-poller.service"
WINDOWS_TASK_STATE_LABELS = {
    0: "unknown",
    1: "disabled",
    2: "queued",
    3: "ready",
    4: "running",
}
SERVICE_RUNTIME_ENV_KEYS = (
    "REINS_RUNTIME_ROOT",
    "HERMES_AGENT_ROOT",
    "HERMES_WEB_UI_SKILLS_DIR",
    "OFFICECLI_BIN",
    "OFFICECLI_SKIP_UPDATE",
    "PLAYWRIGHT_BROWSERS_PATH",
    "PYTHONHOME",
)


def service_plist_path(*, home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"


def windows_task_script_path(*, home: Path | None = None) -> Path:
    return (home or get_reins_home()) / "wecom" / "ticket-poller.ps1"


def linux_poller_script_path(*, home: Path | None = None) -> Path:
    return (home or get_reins_home()) / "wecom" / "ticket-poller.sh"


def systemd_unit_path(*, config_home: Path | None = None) -> Path:
    if config_home is None:
        configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
        config_home = (
            Path(os.path.expandvars(configured)).expanduser()
            if configured
            else Path.home() / ".config"
        )
    return config_home / "systemd" / "user" / SYSTEMD_UNIT_NAME


def service_target() -> str:
    return f"gui/{os.getuid()}/{SERVICE_LABEL}"


def _service_runtime_environment() -> dict[str, str]:
    """Keep bundled-runtime paths available after the desktop app exits.

    Only product runtime paths are persisted. Credentials continue to be read
    from the private Reins .env file by the background process.
    """
    return {
        key: value
        for key in SERVICE_RUNTIME_ENV_KEYS
        if (value := os.environ.get(key, "").strip())
    }


def service_python_path() -> Path:
    """Return a Python path without resolving virtualenv symlinks.

    On Ubuntu, resolving ``.venv/bin/python`` commonly produces
    ``/usr/bin/python3``. Executing that resolved path bypasses the virtual
    environment and cannot import the editable Reins installation.
    """
    candidates: list[Path] = []
    configured = os.environ.get("REINS_SERVICE_PYTHON", "").strip()
    if configured:
        candidates.append(Path(os.path.expandvars(configured)).expanduser())

    virtual_env = os.environ.get("VIRTUAL_ENV", "").strip()
    if virtual_env:
        venv_root = Path(os.path.expandvars(virtual_env)).expanduser()
        candidates.append(
            venv_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )

    project_root = get_project_root()
    candidates.append(
        project_root
        / ".venv"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    candidates.append(Path(sys.executable))

    for candidate in candidates:
        absolute = candidate if candidate.is_absolute() else candidate.absolute()
        if absolute.is_file():
            return absolute
    return Path(sys.executable)


def _service_python_error(python_path: Path) -> str:
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import reins.main"],
            cwd=python_path.parent,
            env=env,
            capture_output=True,
            check=False,
            text=True,
            errors="replace",
            timeout=15,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        return f"could not run service Python {python_path}: {exc}"
    if result.returncode == 0:
        return ""
    detail = (result.stderr or result.stdout or "could not import reins.main").strip()
    return (
        f"service Python cannot import Reins: {python_path}\n{detail}\n"
        "Activate the project virtual environment and run `uv pip install -e .`, "
        "or set REINS_SERVICE_PYTHON to the correct venv Python path."
    )


def _platform_error() -> dict[str, Any] | None:
    if sys.platform in {"darwin", "win32"} or sys.platform.startswith("linux"):
        return None
    return {
        "ok": False,
        "error": "ticket poller service management supports macOS, Windows, and Linux only",
    }


def build_service_definition(*, interval: float = 30.0) -> dict[str, Any]:
    reins_home = get_reins_home()
    logs_dir = reins_home / "logs"
    return {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [
            str(service_python_path()),
            "-m",
            "reins.main",
            "wecom",
            "ticket-api",
            "poll",
            "--watch",
            "--json-lines",
            "--interval",
            str(max(5.0, float(interval))),
        ],
        "EnvironmentVariables": {
            "HERMES_HOME": str(reins_home),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
            "REINS_HOME": str(reins_home),
            **_service_runtime_environment(),
        },
        "KeepAlive": True,
        "ProcessType": "Background",
        "RunAtLoad": True,
        "StandardErrorPath": str(logs_dir / "ticket-poller.error.log"),
        "StandardOutPath": str(logs_dir / "ticket-poller.log"),
        "ThrottleInterval": 10,
    }


def write_service_definition(*, interval: float = 30.0, home: Path | None = None) -> Path:
    plist_path = service_plist_path(home=home)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    get_reins_home().joinpath("logs").mkdir(parents=True, exist_ok=True)
    temporary = plist_path.with_name(f".{plist_path.name}.tmp")
    with temporary.open("wb") as handle:
        plistlib.dump(build_service_definition(interval=interval), handle, sort_keys=True)
    temporary.replace(plist_path)
    return plist_path


def _powershell_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def build_windows_task_script(*, interval: float = 30.0) -> str:
    reins_home = get_reins_home()
    log_path = reins_home / "logs" / "ticket-poller.log"
    arguments = [
        "-m",
        "reins.main",
        "wecom",
        "ticket-api",
        "poll",
        "--watch",
        "--json-lines",
        "--interval",
        str(max(5.0, float(interval))),
    ]
    argument_lines = "\n".join(f"    {_powershell_quote(argument)}" for argument in arguments)
    runtime_environment = [
        f"$env:{key} = {_powershell_quote(value)}"
        for key, value in _service_runtime_environment().items()
    ]
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$ProgressPreference = 'SilentlyContinue'",
            f"$env:REINS_HOME = {_powershell_quote(reins_home)}",
            f"$env:HERMES_HOME = {_powershell_quote(reins_home)}",
            "$env:PYTHONIOENCODING = 'utf-8'",
            "$env:PYTHONUNBUFFERED = '1'",
            "$env:PYTHONUTF8 = '1'",
            *runtime_environment,
            f"$python = {_powershell_quote(service_python_path())}",
            "$arguments = @(",
            argument_lines,
            ")",
            f"$logPath = {_powershell_quote(log_path)}",
            "New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null",
            "& $python @arguments 2>&1 | Out-File -FilePath $logPath -Append -Encoding utf8",
            "exit $LASTEXITCODE",
            "",
        ]
    )


def write_windows_task_script(*, interval: float = 30.0, home: Path | None = None) -> Path:
    script_path = windows_task_script_path(home=home)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    get_reins_home().joinpath("logs").mkdir(parents=True, exist_ok=True)
    temporary = script_path.with_name(f".{script_path.name}.tmp")
    temporary.write_text(build_windows_task_script(interval=interval), encoding="utf-8-sig")
    temporary.replace(script_path)
    return script_path


def build_linux_poller_script(*, interval: float = 30.0) -> str:
    reins_home = get_reins_home()
    logs_dir = reins_home / "logs"
    arguments = [
        str(service_python_path()),
        "-m",
        "reins.main",
        "wecom",
        "ticket-api",
        "poll",
        "--watch",
        "--json-lines",
        "--interval",
        str(max(5.0, float(interval))),
    ]
    command = " ".join(shlex.quote(argument) for argument in arguments)
    runtime_environment = [
        f"export {key}={shlex.quote(value)}"
        for key, value in _service_runtime_environment().items()
    ]
    return "\n".join(
        [
            "#!/bin/sh",
            "set -eu",
            "umask 077",
            f"export REINS_HOME={shlex.quote(str(reins_home))}",
            f"export HERMES_HOME={shlex.quote(str(reins_home))}",
            "export PYTHONIOENCODING=utf-8",
            "export PYTHONUNBUFFERED=1",
            "export PYTHONUTF8=1",
            *runtime_environment,
            f"mkdir -p {shlex.quote(str(logs_dir))}",
            f"exec >>{shlex.quote(str(logs_dir / 'ticket-poller.log'))} "
            f"2>>{shlex.quote(str(logs_dir / 'ticket-poller.error.log'))}",
            f"exec {command}",
            "",
        ]
    )


def write_linux_poller_script(*, interval: float = 30.0, home: Path | None = None) -> Path:
    script_path = linux_poller_script_path(home=home)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = script_path.with_name(f".{script_path.name}.tmp")
    temporary.write_text(build_linux_poller_script(interval=interval), encoding="utf-8")
    temporary.chmod(0o700)
    temporary.replace(script_path)
    return script_path


def _systemd_quote(value: str | Path) -> str:
    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "$$")
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def build_systemd_unit(*, interval: float = 30.0) -> str:
    script_path = linux_poller_script_path()
    return "\n".join(
        [
            "[Unit]",
            "Description=Reins WeCom Ticket Poller",
            "StartLimitIntervalSec=0",
            "",
            "[Service]",
            "Type=simple",
            f"ExecStart={_systemd_quote(script_path)}",
            "Restart=always",
            "RestartSec=10",
            "KillMode=control-group",
            "TimeoutStopSec=30",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def write_systemd_unit(
    *,
    interval: float = 30.0,
    config_home: Path | None = None,
) -> Path:
    unit_path = systemd_unit_path(config_home=config_home)
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = unit_path.with_name(f".{unit_path.name}.tmp")
    temporary.write_text(build_systemd_unit(interval=interval), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(unit_path)
    return unit_path


def _launchctl(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *arguments],
        capture_output=True,
        check=False,
        text=True,
    )


def _schtasks(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        ["schtasks.exe", *arguments],
        capture_output=True,
        check=False,
        text=True,
        encoding="oem" if os.name == "nt" else None,
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags,
    )


def _powershell(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        ["powershell.exe", *arguments],
        capture_output=True,
        check=False,
        text=True,
        encoding="oem" if os.name == "nt" else None,
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags,
    )


def _systemctl(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    command = ["systemctl", "--user", *arguments]
    try:
        return subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            errors="replace",
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            command,
            returncode=127,
            stdout="",
            stderr="systemctl was not found; install and boot Ubuntu with systemd",
        )


def _command_error(result: subprocess.CompletedProcess[str], command: str) -> str:
    return (result.stderr or result.stdout or f"{command} exited {result.returncode}").strip()


def _windows_task_exists() -> bool:
    return _schtasks(["/Query", "/TN", WINDOWS_TASK_NAME]).returncode == 0


def _windows_task_state() -> tuple[int | None, str]:
    command = (
        f"$task = Get-ScheduledTask -TaskName {_powershell_quote(WINDOWS_TASK_NAME)} "
        "-ErrorAction Stop; Write-Output ([int]$task.State)"
    )
    result = _powershell(
        [
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    )
    if result.returncode != 0:
        return None, _command_error(result, "powershell.exe")
    for line in reversed((result.stdout or "").splitlines()):
        clean = line.strip()
        if clean.isdigit():
            return int(clean), ""
    return None, "could not determine Windows scheduled task state"


def _windows_task_arguments(script_path: Path) -> str:
    return subprocess.list2cmdline(
        [
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
    )


def _register_windows_task(script_path: Path) -> subprocess.CompletedProcess[str]:
    action_arguments = _windows_task_arguments(script_path)
    command = (
        "$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name; "
        f"Stop-ScheduledTask -TaskName {_powershell_quote(WINDOWS_TASK_NAME)} -ErrorAction SilentlyContinue; "
        "$powershell = Join-Path $env:SystemRoot "
        "'System32\\WindowsPowerShell\\v1.0\\powershell.exe'; "
        "$action = New-ScheduledTaskAction "
        "-Execute $powershell "
        f"-Argument {_powershell_quote(action_arguments)}; "
        "$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user; "
        "$principal = New-ScheduledTaskPrincipal "
        "-UserId $user -LogonType Interactive -RunLevel Limited; "
        "$settings = New-ScheduledTaskSettingsSet "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) "
        "-RestartCount 999 "
        "-RestartInterval (New-TimeSpan -Minutes 1) "
        "-MultipleInstances IgnoreNew "
        "-StartWhenAvailable "
        "-AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries; "
        f"Register-ScheduledTask -TaskName {_powershell_quote(WINDOWS_TASK_NAME)} "
        "-Action $action -Trigger $trigger -Principal $principal "
        "-Settings $settings -Description 'Reins WeCom ticket poller' "
        "-Force | Out-Null; "
        f"Start-ScheduledTask -TaskName {_powershell_quote(WINDOWS_TASK_NAME)}"
    )
    return _powershell(
        [
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    )


def _windows_service_details() -> dict[str, Any]:
    reins_home = get_reins_home()
    return {
        "task_name": WINDOWS_TASK_NAME,
        "script_path": str(windows_task_script_path()),
        "log_path": str(reins_home / "logs" / "ticket-poller.log"),
        "error_log_path": str(reins_home / "logs" / "ticket-poller.log"),
    }


def _install_windows_service(*, interval: float) -> dict[str, Any]:
    script_path = write_windows_task_script(interval=interval)
    registered = _register_windows_task(script_path)
    if registered.returncode != 0:
        return {
            "ok": False,
            "installed": _windows_task_exists(),
            "running": False,
            **_windows_service_details(),
            "error": _command_error(registered, "powershell.exe"),
        }

    return {
        "ok": True,
        "installed": True,
        "running": True,
        **_windows_service_details(),
        "error": "",
    }


def _linux_service_details() -> dict[str, Any]:
    reins_home = get_reins_home()
    return {
        "unit_name": SYSTEMD_UNIT_NAME,
        "unit_path": str(systemd_unit_path()),
        "script_path": str(linux_poller_script_path()),
        "log_path": str(reins_home / "logs" / "ticket-poller.log"),
        "error_log_path": str(reins_home / "logs" / "ticket-poller.error.log"),
    }


def _install_linux_service(*, interval: float) -> dict[str, Any]:
    write_linux_poller_script(interval=interval)
    write_systemd_unit(interval=interval)

    reloaded = _systemctl(["daemon-reload"])
    if reloaded.returncode != 0:
        return {
            "ok": False,
            "installed": True,
            "running": False,
            **_linux_service_details(),
            "error": _command_error(reloaded, "systemctl --user daemon-reload"),
        }

    enabled = _systemctl(["enable", SYSTEMD_UNIT_NAME])
    if enabled.returncode != 0:
        return {
            "ok": False,
            "installed": True,
            "running": False,
            **_linux_service_details(),
            "error": _command_error(enabled, "systemctl --user enable"),
        }

    started = _systemctl(["restart", SYSTEMD_UNIT_NAME])
    return {
        "ok": started.returncode == 0,
        "installed": True,
        "running": started.returncode == 0,
        **_linux_service_details(),
        "error": "" if started.returncode == 0 else _command_error(
            started,
            "systemctl --user restart",
        ),
    }


def install_service(*, interval: float = 30.0) -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    python_path = service_python_path()
    python_error = _service_python_error(python_path)
    if python_error:
        return {
            "ok": False,
            "installed": False,
            "running": False,
            "python_path": str(python_path),
            "error": python_error,
        }
    if sys.platform == "win32":
        return _install_windows_service(interval=interval)
    if sys.platform.startswith("linux"):
        return _install_linux_service(interval=interval)

    plist_path = write_service_definition(interval=interval)
    _launchctl(["bootout", service_target()])
    result = _launchctl(["bootstrap", f"gui/{os.getuid()}", str(plist_path)])
    if result.returncode != 0:
        return {
            "ok": False,
            "installed": True,
            "running": False,
            "plist_path": str(plist_path),
            "error": _command_error(result, "launchctl"),
        }
    return {
        "ok": True,
        "installed": True,
        "running": True,
        "plist_path": str(plist_path),
        "label": SERVICE_LABEL,
    }


def _start_windows_service() -> dict[str, Any]:
    if not _windows_task_exists():
        return {
            "ok": False,
            "installed": False,
            "running": False,
            **_windows_service_details(),
            "error": "service is not installed; run `reins wecom ticket-api service install`",
        }
    result = _schtasks(["/Run", "/TN", WINDOWS_TASK_NAME])
    return {
        "ok": result.returncode == 0,
        "installed": True,
        "running": result.returncode == 0,
        **_windows_service_details(),
        "error": "" if result.returncode == 0 else _command_error(result, "schtasks.exe"),
    }


def _start_linux_service() -> dict[str, Any]:
    if not systemd_unit_path().is_file():
        return {
            "ok": False,
            "installed": False,
            "running": False,
            **_linux_service_details(),
            "error": "service is not installed; run `reins wecom ticket-api service install`",
        }
    reloaded = _systemctl(["daemon-reload"])
    if reloaded.returncode != 0:
        return {
            "ok": False,
            "installed": True,
            "running": False,
            **_linux_service_details(),
            "error": _command_error(reloaded, "systemctl --user daemon-reload"),
        }
    started = _systemctl(["start", SYSTEMD_UNIT_NAME])
    return {
        "ok": started.returncode == 0,
        "installed": True,
        "running": started.returncode == 0,
        **_linux_service_details(),
        "error": "" if started.returncode == 0 else _command_error(
            started,
            "systemctl --user start",
        ),
    }


def start_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _start_windows_service()
    if sys.platform.startswith("linux"):
        return _start_linux_service()

    plist_path = service_plist_path()
    if not plist_path.is_file():
        return {
            "ok": False,
            "installed": False,
            "running": False,
            "plist_path": str(plist_path),
            "error": "service is not installed; run `reins wecom ticket-api service install`",
        }

    result = _launchctl(["bootstrap", f"gui/{os.getuid()}", str(plist_path)])
    if result.returncode != 0:
        result = _launchctl(["kickstart", "-k", service_target()])
    return {
        "ok": result.returncode == 0,
        "installed": True,
        "running": result.returncode == 0,
        "plist_path": str(plist_path),
        "error": "" if result.returncode == 0 else _command_error(result, "launchctl"),
    }


def _stop_windows_service() -> dict[str, Any]:
    if not _windows_task_exists():
        return {
            "ok": True,
            "installed": False,
            "running": False,
            **_windows_service_details(),
            "error": "",
        }
    state, state_error = _windows_task_state()
    if state != 4:
        if state_error:
            result = _schtasks(["/End", "/TN", WINDOWS_TASK_NAME])
            return {
                "ok": result.returncode == 0,
                "installed": True,
                "running": False,
                **_windows_service_details(),
                "error": "" if result.returncode == 0 else _command_error(result, "schtasks.exe"),
            }
        return {
            "ok": True,
            "installed": True,
            "running": False,
            **_windows_service_details(),
            "error": "",
        }
    result = _schtasks(["/End", "/TN", WINDOWS_TASK_NAME])
    return {
        "ok": result.returncode == 0,
        "installed": True,
        "running": False,
        **_windows_service_details(),
        "error": "" if result.returncode == 0 else _command_error(result, "schtasks.exe"),
    }


def _stop_linux_service() -> dict[str, Any]:
    if not systemd_unit_path().is_file():
        return {
            "ok": True,
            "installed": False,
            "running": False,
            **_linux_service_details(),
            "error": "",
        }
    stopped = _systemctl(["stop", SYSTEMD_UNIT_NAME])
    return {
        "ok": stopped.returncode == 0,
        "installed": True,
        "running": False,
        **_linux_service_details(),
        "error": "" if stopped.returncode == 0 else _command_error(
            stopped,
            "systemctl --user stop",
        ),
    }


def stop_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _stop_windows_service()
    if sys.platform.startswith("linux"):
        return _stop_linux_service()

    result = _launchctl(["bootout", service_target()])
    error = _command_error(result, "launchctl")
    not_loaded = "could not find service" in error.lower() or "no such process" in error.lower()
    return {
        "ok": result.returncode == 0 or not_loaded,
        "installed": service_plist_path().is_file(),
        "running": False,
        "plist_path": str(service_plist_path()),
        "error": "" if result.returncode == 0 or not_loaded else error,
    }


def _windows_service_status() -> dict[str, Any]:
    if not _windows_task_exists():
        return {
            "ok": True,
            "installed": False,
            "loaded": False,
            "running": False,
            "state": "not_installed",
            **_windows_service_details(),
            "error": "",
        }
    state, state_error = _windows_task_state()
    return {
        "ok": not state_error,
        "installed": True,
        "loaded": True,
        "running": state == 4,
        "state": WINDOWS_TASK_STATE_LABELS.get(state or 0, "unknown"),
        **_windows_service_details(),
        "error": state_error,
    }


def _linux_service_status() -> dict[str, Any]:
    unit_path = systemd_unit_path()
    if not unit_path.is_file():
        return {
            "ok": True,
            "installed": False,
            "loaded": False,
            "running": False,
            "state": "not_installed",
            "pid": None,
            **_linux_service_details(),
            "error": "",
        }

    result = _systemctl(
        [
            "show",
            SYSTEMD_UNIT_NAME,
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            "--property=MainPID",
            "--no-pager",
        ]
    )
    properties: dict[str, str] = {}
    for line in (result.stdout or "").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key.strip()] = value.strip()
    raw_pid = properties.get("MainPID", "")
    pid = int(raw_pid) if raw_pid.isdigit() and raw_pid != "0" else None
    active_state = properties.get("ActiveState", "")
    sub_state = properties.get("SubState", "")
    return {
        "ok": result.returncode == 0,
        "installed": True,
        "loaded": properties.get("LoadState") == "loaded",
        "running": active_state == "active",
        "state": sub_state or active_state or "unknown",
        "pid": pid,
        **_linux_service_details(),
        "error": "" if result.returncode == 0 else _command_error(
            result,
            "systemctl --user show",
        ),
    }


def service_status() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _windows_service_status()
    if sys.platform.startswith("linux"):
        return _linux_service_status()

    plist_path = service_plist_path()
    result = _launchctl(["print", service_target()])
    output = result.stdout or ""
    pid_match = re.search(r"\bpid\s*=\s*(\d+)", output)
    state_match = re.search(r"\bstate\s*=\s*([^\n]+)", output)
    return {
        "ok": True,
        "installed": plist_path.is_file(),
        "loaded": result.returncode == 0,
        "running": bool(pid_match),
        "pid": int(pid_match.group(1)) if pid_match else None,
        "state": state_match.group(1).strip() if state_match else "",
        "plist_path": str(plist_path),
        "log_path": str(get_reins_home() / "logs" / "ticket-poller.log"),
        "error_log_path": str(get_reins_home() / "logs" / "ticket-poller.error.log"),
    }


def _uninstall_windows_service() -> dict[str, Any]:
    stopped = _stop_windows_service()
    if not stopped.get("ok"):
        return stopped

    if _windows_task_exists():
        deleted = _schtasks(["/Delete", "/TN", WINDOWS_TASK_NAME, "/F"])
        if deleted.returncode != 0:
            return {
                "ok": False,
                "installed": True,
                "running": False,
                **_windows_service_details(),
                "error": _command_error(deleted, "schtasks.exe"),
            }

    script_path = windows_task_script_path()
    try:
        script_path.unlink()
    except FileNotFoundError:
        pass
    return {
        "ok": True,
        "installed": False,
        "running": False,
        **_windows_service_details(),
        "error": "",
    }


def _uninstall_linux_service() -> dict[str, Any]:
    unit_path = systemd_unit_path()
    script_path = linux_poller_script_path()
    if unit_path.is_file():
        disabled = _systemctl(["disable", "--now", SYSTEMD_UNIT_NAME])
        if disabled.returncode != 0:
            return {
                "ok": False,
                "installed": True,
                "running": False,
                **_linux_service_details(),
                "error": _command_error(
                    disabled,
                    "systemctl --user disable --now",
                ),
            }

    for path in (unit_path, script_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    reloaded = _systemctl(["daemon-reload"])
    _systemctl(["reset-failed", SYSTEMD_UNIT_NAME])
    return {
        "ok": reloaded.returncode == 0,
        "installed": False,
        "running": False,
        **_linux_service_details(),
        "error": "" if reloaded.returncode == 0 else _command_error(
            reloaded,
            "systemctl --user daemon-reload",
        ),
    }


def uninstall_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _uninstall_windows_service()
    if sys.platform.startswith("linux"):
        return _uninstall_linux_service()

    stopped = stop_service()
    plist_path = service_plist_path()
    try:
        plist_path.unlink()
    except FileNotFoundError:
        pass
    return {
        "ok": bool(stopped.get("ok")),
        "installed": False,
        "running": False,
        "plist_path": str(plist_path),
        "error": stopped.get("error", ""),
    }
