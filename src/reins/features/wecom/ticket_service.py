from __future__ import annotations

import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
from typing import Any, Sequence

from reins.api.home import get_reins_home


SERVICE_LABEL = "ai.reins.wecom-ticket-poller"
WINDOWS_TASK_NAME = "Reins WeCom Ticket Poller"
WINDOWS_TASK_STATE_LABELS = {
    0: "unknown",
    1: "disabled",
    2: "queued",
    3: "ready",
    4: "running",
}


def service_plist_path(*, home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"


def windows_task_script_path(*, home: Path | None = None) -> Path:
    return (home or get_reins_home()) / "wecom" / "ticket-poller.ps1"


def service_target() -> str:
    return f"gui/{os.getuid()}/{SERVICE_LABEL}"


def _platform_error() -> dict[str, Any] | None:
    if sys.platform in {"darwin", "win32"}:
        return None
    return {
        "ok": False,
        "error": "ticket poller service management supports macOS and Windows only",
    }


def build_service_definition(*, interval: float = 30.0) -> dict[str, Any]:
    reins_home = get_reins_home()
    logs_dir = reins_home / "logs"
    return {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [
            sys.executable,
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
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$ProgressPreference = 'SilentlyContinue'",
            f"$env:REINS_HOME = {_powershell_quote(reins_home)}",
            f"$env:HERMES_HOME = {_powershell_quote(reins_home)}",
            "$env:PYTHONIOENCODING = 'utf-8'",
            "$env:PYTHONUNBUFFERED = '1'",
            "$env:PYTHONUTF8 = '1'",
            f"$python = {_powershell_quote(Path(sys.executable).resolve())}",
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
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags,
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


def _windows_task_action(script_path: Path) -> str:
    return subprocess.list2cmdline(
        [
            "powershell.exe",
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


def _configure_windows_task() -> subprocess.CompletedProcess[str]:
    command = (
        "$settings = New-ScheduledTaskSettingsSet "
        "-ExecutionTimeLimit ([TimeSpan]::Zero) "
        "-RestartCount 999 "
        "-RestartInterval (New-TimeSpan -Minutes 1) "
        "-MultipleInstances IgnoreNew "
        "-StartWhenAvailable "
        "-AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries; "
        f"Set-ScheduledTask -TaskName {_powershell_quote(WINDOWS_TASK_NAME)} "
        "-Settings $settings | Out-Null"
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
    created = _schtasks(
        [
            "/Create",
            "/TN",
            WINDOWS_TASK_NAME,
            "/SC",
            "ONLOGON",
            "/RL",
            "LIMITED",
            "/IT",
            "/TR",
            _windows_task_action(script_path),
            "/F",
        ]
    )
    if created.returncode != 0:
        return {
            "ok": False,
            "installed": _windows_task_exists(),
            "running": False,
            **_windows_service_details(),
            "error": _command_error(created, "schtasks.exe"),
        }

    configured = _configure_windows_task()
    if configured.returncode != 0:
        return {
            "ok": False,
            "installed": True,
            "running": False,
            **_windows_service_details(),
            "error": _command_error(configured, "powershell.exe"),
        }

    started = _schtasks(["/Run", "/TN", WINDOWS_TASK_NAME])
    return {
        "ok": started.returncode == 0,
        "installed": True,
        "running": started.returncode == 0,
        **_windows_service_details(),
        "error": "" if started.returncode == 0 else _command_error(started, "schtasks.exe"),
    }


def install_service(*, interval: float = 30.0) -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _install_windows_service(interval=interval)

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


def start_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _start_windows_service()

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


def stop_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _stop_windows_service()

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


def service_status() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _windows_service_status()

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


def uninstall_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    if sys.platform == "win32":
        return _uninstall_windows_service()

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
