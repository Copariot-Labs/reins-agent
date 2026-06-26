from __future__ import annotations

import platform
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

from reins.features.workmode.proof import capture_desktop_screenshot


def _open_command_for_path(path: str) -> list[str] | None:
    system = platform.system().lower()

    if system == "darwin":
        return ["open", path]

    if system == "linux" and shutil.which("xdg-open"):
        return ["xdg-open", path]

    if system == "windows":
        return ["cmd", "/c", "start", "", path]

    return None


def _open_command_for_url(url: str) -> list[str] | None:
    system = platform.system().lower()

    if system == "darwin":
        return ["open", url]

    if system == "linux" and shutil.which("xdg-open"):
        return ["xdg-open", url]

    if system == "windows":
        return ["cmd", "/c", "start", "", url]

    return None


def present_file(
    *,
    case_id: str,
    path: str,
    title: str | None = None,
    hold_seconds: float = 2.0,
    capture_proof: bool = True,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "kind": "office_present",
        "target": path,
        "title": title or Path(path).name,
        "visible": True,
        "platform": platform.system().lower(),
    }

    command = _open_command_for_path(path)
    if command is None:
        action.update({
            "ok": False,
            "error": "No supported desktop opener is available on this platform.",
        })
        return action

    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        action.update({"ok": True, "command": command})
        if hold_seconds > 0:
            time.sleep(hold_seconds)
    except Exception as exc:
        action.update({
            "ok": False,
            "command": command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        return action

    if capture_proof:
        screenshot = capture_desktop_screenshot(case_id=case_id, label="office-present")
        action["screenshot"] = screenshot

    return action


def present_url(
    *,
    case_id: str,
    url: str,
    title: str | None = None,
    hold_seconds: float = 2.0,
    capture_proof: bool = True,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "kind": "browser_present",
        "target": url,
        "title": title or url,
        "visible": True,
        "platform": platform.system().lower(),
    }

    command = _open_command_for_url(url)

    try:
        if command is not None:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            action.update({"ok": True, "command": command})
        else:
            opened = webbrowser.open(url)
            action.update({"ok": opened, "command": "webbrowser.open"})

        if hold_seconds > 0:
            time.sleep(hold_seconds)
    except Exception as exc:
        action.update({
            "ok": False,
            "command": command or "webbrowser.open",
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        return action

    if capture_proof:
        screenshot = capture_desktop_screenshot(case_id=case_id, label="browser-present")
        action["screenshot"] = screenshot

    return action
