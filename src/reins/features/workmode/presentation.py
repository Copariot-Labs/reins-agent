from __future__ import annotations

from pathlib import Path
from typing import Any

from reins.features.workmode.desktop_window import DesktopWindowLayer
from reins.features.workmode.proof import capture_desktop_screenshot


def present_file(
    *,
    case_id: str,
    path: str,
    title: str | None = None,
    hold_seconds: float = 2.0,
    capture_proof: bool = True,
) -> dict[str, Any]:
    layer = DesktopWindowLayer(case_id=case_id, visible=True, hold_seconds=hold_seconds)
    action: dict[str, Any] = {
        "kind": "office_present",
        "target": path,
        "title": title or Path(path).name,
        "visible": True,
        "platform": layer.platform,
    }

    opened = layer.open_path(path, proof_label="office-present")
    action.update({
        "ok": opened.get("ok"),
        "status": opened.get("status"),
        "command": opened.get("command"),
        "error": opened.get("error"),
        "error_type": opened.get("error_type"),
        "desktop_action": opened,
    })

    if capture_proof:
        screenshot = action.get("screenshot")
        if not isinstance(screenshot, dict):
            screenshot = opened.get("screenshot")
        if not isinstance(screenshot, dict):
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
    layer = DesktopWindowLayer(case_id=case_id, visible=True, hold_seconds=hold_seconds)
    action: dict[str, Any] = {
        "kind": "browser_present",
        "target": url,
        "title": title or url,
        "visible": True,
        "platform": layer.platform,
    }

    opened = layer.open_url(url, proof_label="browser-present")
    action.update({
        "ok": opened.get("ok"),
        "status": opened.get("status"),
        "command": opened.get("command"),
        "error": opened.get("error"),
        "error_type": opened.get("error_type"),
        "desktop_action": opened,
    })

    if capture_proof:
        screenshot = action.get("screenshot")
        if not isinstance(screenshot, dict):
            screenshot = opened.get("screenshot")
        if not isinstance(screenshot, dict):
            screenshot = capture_desktop_screenshot(case_id=case_id, label="browser-present")
        action["screenshot"] = screenshot

    return action
