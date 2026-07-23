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


def service_plist_path(*, home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"


def service_target() -> str:
    return f"gui/{os.getuid()}/{SERVICE_LABEL}"


def _platform_error() -> dict[str, Any] | None:
    if sys.platform == "darwin":
        return None
    return {
        "ok": False,
        "error": "ticket poller service management currently supports macOS launchd only",
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
            "PYTHONUNBUFFERED": "1",
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


def _launchctl(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["launchctl", *arguments],
        capture_output=True,
        check=False,
        text=True,
    )


def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or f"launchctl exited {result.returncode}").strip()


def install_service(*, interval: float = 30.0) -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    plist_path = write_service_definition(interval=interval)
    _launchctl(["bootout", service_target()])
    result = _launchctl(["bootstrap", f"gui/{os.getuid()}", str(plist_path)])
    if result.returncode != 0:
        return {
            "ok": False,
            "installed": True,
            "running": False,
            "plist_path": str(plist_path),
            "error": _command_error(result),
        }
    return {
        "ok": True,
        "installed": True,
        "running": True,
        "plist_path": str(plist_path),
        "label": SERVICE_LABEL,
    }


def start_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
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
        "error": "" if result.returncode == 0 else _command_error(result),
    }


def stop_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
    result = _launchctl(["bootout", service_target()])
    error = _command_error(result)
    not_loaded = "could not find service" in error.lower() or "no such process" in error.lower()
    return {
        "ok": result.returncode == 0 or not_loaded,
        "installed": service_plist_path().is_file(),
        "running": False,
        "plist_path": str(service_plist_path()),
        "error": "" if result.returncode == 0 or not_loaded else error,
    }


def service_status() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
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


def uninstall_service() -> dict[str, Any]:
    unsupported = _platform_error()
    if unsupported:
        return unsupported
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
