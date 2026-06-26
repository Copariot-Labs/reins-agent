from __future__ import annotations

import platform
import shutil
import subprocess
import time

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.proof import capture_desktop_screenshot, write_proof_manifest
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


def _open_desktop_app(app_name: str) -> dict:
    system = platform.system().lower()
    action = {
        "kind": "desktop_app_open",
        "app_name": app_name,
        "visible": True,
        "platform": system,
    }

    command: list[str] | None = None
    if system == "darwin":
        command = ["open", "-a", app_name]
    elif system == "linux":
        executable = (
            shutil.which(app_name)
            or shutil.which(app_name.lower())
            or shutil.which(app_name.lower().replace(" ", "-"))
            or shutil.which(app_name.lower().replace(" ", ""))
        )
        if executable:
            command = [executable]
    elif system == "windows":
        command = ["cmd", "/c", "start", "", app_name]

    if command is None:
        return {
            **action,
            "ok": False,
            "error": f"No supported desktop opener for application: {app_name}",
        }

    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.0)
        return {
            **action,
            "ok": True,
            "command": command,
        }
    except Exception as exc:
        return {
            **action,
            "ok": False,
            "command": command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    intake = state.scratch.get("intake", {})
    case_id = intake.get("case_id") or state.task_id
    app_name = str(step.metadata.get("app_name") or "").strip()
    visible = bool(step.visible_action and state.mode_policy.visible_actions)

    desktop_actions = []
    if app_name:
        if visible:
            desktop_actions.append(_open_desktop_app(app_name))
        else:
            desktop_actions.append({
                "kind": "desktop_app_open_skipped",
                "app_name": app_name,
                "visible": False,
                "ok": True,
                "skipped": True,
                "reason": "visible actions are disabled for this WorkMode run",
            })

    screenshot = capture_desktop_screenshot(
        case_id=case_id,
        label="desktop",
    )

    proofs = [screenshot]

    manifest = write_proof_manifest(
        case_id=case_id,
        proofs=proofs,
    )

    screenshots: list[str] = []

    if screenshot.get("ok") and screenshot.get("path"):
        screenshots.append(str(screenshot["path"]))

    action_failed = any(action.get("ok") is False for action in desktop_actions)
    ok = bool(screenshot.get("ok")) and not action_failed

    return {
        "ok": ok,
        "worker": "desktop_capture",
        "step_id": step.id,
        "message": "Desktop action proof captured."
        if ok
        else "Desktop action or proof capture failed.",
        "screenshots": screenshots,
        "desktop_actions": desktop_actions,
        "proofs": proofs,
        "proof_manifest": manifest,
    }


registry.register("desktop_capture", run)
