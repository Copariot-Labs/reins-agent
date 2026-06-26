from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Any

from reins.features.workmode.proof import capture_desktop_screenshot
from reins.features.workmode.workers.ocr.engine import extract_text_from_image


def _run_applescript(script: str, timeout: int = 10) -> dict[str, Any]:
    if not shutil.which("osascript"):
        return {
            "ok": False,
            "error": "osascript is not available.",
        }

    proc = subprocess.run(
        ["osascript", "-e", script],
        text=True,
        capture_output=True,
        timeout=timeout,
    )

    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "returncode": proc.returncode,
    }


def _set_clipboard(text: str) -> dict[str, Any]:
    system = platform.system().lower()

    if system == "darwin" and shutil.which("pbcopy"):
        proc = subprocess.run(["pbcopy"], input=text, text=True, capture_output=True, timeout=10)
        return {
            "ok": proc.returncode == 0,
            "tool": "pbcopy",
            "error": proc.stderr.strip(),
        }

    if system == "linux":
        if shutil.which("wl-copy"):
            proc = subprocess.run(["wl-copy"], input=text, text=True, capture_output=True, timeout=10)
            return {"ok": proc.returncode == 0, "tool": "wl-copy", "error": proc.stderr.strip()}
        if shutil.which("xclip"):
            proc = subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, capture_output=True, timeout=10)
            return {"ok": proc.returncode == 0, "tool": "xclip", "error": proc.stderr.strip()}

    if system == "windows" and shutil.which("powershell"):
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard"],
            input=text,
            text=True,
            capture_output=True,
            timeout=10,
        )
        return {"ok": proc.returncode == 0, "tool": "powershell Set-Clipboard", "error": proc.stderr.strip()}

    return {
        "ok": False,
        "error": "No supported clipboard command is available.",
    }


def _activate_wechat_macos() -> dict[str, Any]:
    last_error = ""
    for app_name in ("WeChat", "微信"):
        proc = subprocess.run(
            ["open", "-a", app_name],
            text=True,
            capture_output=True,
            timeout=15,
        )
        if proc.returncode == 0:
            time.sleep(1.0)
            return {"ok": True, "app": app_name, "method": "open -a"}
        last_error = proc.stderr.strip() or proc.stdout.strip()

    script = 'tell application "WeChat" to activate'
    result = _run_applescript(script)
    if result.get("ok"):
        time.sleep(1.0)
        return {"ok": True, "app": "WeChat", "method": "osascript"}

    return {
        "ok": False,
        "error": last_error or result.get("stderr") or "Unable to activate WeChat.",
    }


def _keystroke_macos(key: str, *, command: bool = False, timeout: int = 10) -> dict[str, Any]:
    modifier = " using command down" if command else ""
    script = f'tell application "System Events" to keystroke "{key}"{modifier}'
    return _run_applescript(script, timeout=timeout)


def _key_code_macos(code: int, *, command: bool = False, timeout: int = 10) -> dict[str, Any]:
    modifier = " using command down" if command else ""
    script = f'tell application "System Events" to key code {code}{modifier}'
    return _run_applescript(script, timeout=timeout)


def _ocr_latest_screenshot(case_id: str, label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    screenshot = capture_desktop_screenshot(case_id=case_id, label=label)
    if not screenshot.get("ok") or not screenshot.get("path"):
        return screenshot, {
            "ok": False,
            "error": screenshot.get("error") or "No screenshot available for OCR.",
        }

    ocr = extract_text_from_image(str(screenshot["path"]))
    return screenshot, ocr


def send_wechat_message_after_confirmation(
    *,
    case_id: str,
    confirmation: dict[str, Any],
) -> dict[str, Any]:
    target = str(confirmation.get("target") or "").strip()
    payload = confirmation.get("payload") if isinstance(confirmation.get("payload"), dict) else {}
    draft_message = str(payload.get("message") or "").strip()

    result: dict[str, Any] = {
        "ok": False,
        "channel": "wechat",
        "action": "send_message",
        "confirmation_id": confirmation.get("id"),
        "target": target,
        "status": "not_started",
        "desktop_actions": [],
        "screenshots": [],
        "ocr": [],
    }

    if not target or not draft_message:
        result.update({
            "status": "invalid_confirmation",
            "error": "Confirmation must include target and payload.message.",
        })
        return result

    if platform.system().lower() != "darwin":
        result.update({
            "status": "unsupported_platform",
            "error": "The current WeChat UI sender is implemented for macOS automation first.",
        })
        return result

    activate = _activate_wechat_macos()
    result["desktop_actions"].append({"kind": "wechat_activate", **activate})
    if not activate.get("ok"):
        result.update({"status": "activation_failed", "error": activate.get("error")})
        return result

    clipboard = _set_clipboard(target)
    result["desktop_actions"].append({"kind": "clipboard_set_target", **clipboard})
    if not clipboard.get("ok"):
        result.update({"status": "clipboard_failed", "error": clipboard.get("error")})
        return result

    result["desktop_actions"].append({"kind": "wechat_search_shortcut", **_keystroke_macos("f", command=True)})
    time.sleep(0.4)
    result["desktop_actions"].append({"kind": "wechat_paste_target", **_keystroke_macos("v", command=True)})
    time.sleep(0.4)
    result["desktop_actions"].append({"kind": "wechat_open_target", **_key_code_macos(36)})
    time.sleep(1.2)

    screenshot, ocr = _ocr_latest_screenshot(case_id, "wechat-target")
    result["ocr"].append(ocr)
    if screenshot.get("ok") and screenshot.get("path"):
        result["screenshots"].append(str(screenshot["path"]))

    ocr_text = str(ocr.get("text") or "")
    if not ocr.get("ok") or target.lower() not in ocr_text.lower():
        result.update({
            "status": "verification_failed",
            "error": "OCR could not verify the WeChat chat target. Message was not sent.",
            "verification_required": confirmation.get("verification_required"),
        })
        return result

    clipboard = _set_clipboard(draft_message)
    result["desktop_actions"].append({"kind": "clipboard_set_message", **clipboard})
    if not clipboard.get("ok"):
        result.update({"status": "clipboard_failed", "error": clipboard.get("error")})
        return result

    result["desktop_actions"].append({"kind": "wechat_paste_message", **_keystroke_macos("v", command=True)})
    time.sleep(0.5)
    result["desktop_actions"].append({"kind": "wechat_send_message", **_key_code_macos(36)})
    time.sleep(0.8)

    after_screenshot, after_ocr = _ocr_latest_screenshot(case_id, "wechat-sent")
    result["ocr"].append(after_ocr)
    if after_screenshot.get("ok") and after_screenshot.get("path"):
        result["screenshots"].append(str(after_screenshot["path"]))

    result.update({
        "ok": True,
        "status": "sent",
        "sent": True,
    })
    return result
