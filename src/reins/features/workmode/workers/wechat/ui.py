from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Any

from reins.features.workmode.desktop_vision import DesktopVisionLayer
from reins.features.workmode.desktop_window import DesktopWindowLayer
from reins.features.workmode.proof import write_proof_manifest


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


def _append_vision_result(result: dict[str, Any], vision_result: dict[str, Any]) -> None:
    result.setdefault("vision", []).append(vision_result)

    ocr = vision_result.get("ocr")
    if isinstance(ocr, dict):
        result.setdefault("ocr", []).append({
            **ocr,
            "verification": vision_result.get("verification"),
            "vision_kind": vision_result.get("kind"),
        })

    for path in vision_result.get("screenshots") or []:
        if path and path not in result.setdefault("screenshots", []):
            result["screenshots"].append(str(path))

    for action in vision_result.get("actions") or []:
        if isinstance(action, dict):
            result.setdefault("desktop_actions", []).append(action)


def _screenshot_proofs(result: dict[str, Any]) -> list[dict[str, Any]]:
    proofs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in result.get("screenshots") or []:
        if not path or path in seen:
            continue
        seen.add(str(path))
        proofs.append({
            "ok": True,
            "kind": "screenshot",
            "path": str(path),
            "source": "wechat_ui",
        })
    return proofs


def _append_required_action(
    result: dict[str, Any],
    action: dict[str, Any],
    *,
    status: str,
    error: str,
) -> bool:
    result.setdefault("desktop_actions", []).append(action)
    if action.get("ok") is False:
        result.update({
            "status": status,
            "error": action.get("error") or action.get("stderr") or error,
        })
        return False
    return True


def _activate_wechat_with_desktop_layer(case_id: str) -> dict[str, Any]:
    layer = DesktopWindowLayer(case_id=case_id, visible=True, hold_seconds=0.6)
    actions: list[dict[str, Any]] = []

    for app_name in ("WeChat", "微信"):
        opened = layer.open_app(app_name, proof_label="wechat-activate")
        actions.append(opened)
        if opened.get("ok"):
            focused = layer.focus_app(app_name, proof_label="wechat-focus")
            actions.append(focused)
            return {
                "ok": True,
                "app": app_name,
                "method": "desktop_window_layer",
                "desktop_actions": actions,
            }

    fallback = _activate_wechat_macos()
    actions.append({"kind": "wechat_activate_fallback", **fallback})
    return {
        "ok": bool(fallback.get("ok")),
        "app": fallback.get("app"),
        "method": fallback.get("method") or "fallback",
        "desktop_actions": actions,
        "error": fallback.get("error"),
    }


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
        "vision": [],
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

    activate = _activate_wechat_with_desktop_layer(case_id)
    result["desktop_actions"].extend(activate.get("desktop_actions") or [])
    result["desktop_actions"].append({
        "kind": "wechat_activate",
        "ok": bool(activate.get("ok")),
        "app": activate.get("app"),
        "method": activate.get("method"),
        "error": activate.get("error"),
    })
    if not activate.get("ok"):
        result.update({"status": "activation_failed", "error": activate.get("error")})
        return result

    clipboard = _set_clipboard(target)
    result["desktop_actions"].append({"kind": "clipboard_set_target", **clipboard})
    if not clipboard.get("ok"):
        result.update({"status": "clipboard_failed", "error": clipboard.get("error")})
        return result

    if not _append_required_action(
        result,
        {"kind": "wechat_search_shortcut", **_keystroke_macos("f", command=True)},
        status="keyboard_failed",
        error="Unable to open WeChat search.",
    ):
        return result
    time.sleep(0.4)
    if not _append_required_action(
        result,
        {"kind": "wechat_paste_target", **_keystroke_macos("v", command=True)},
        status="keyboard_failed",
        error="Unable to paste the WeChat target.",
    ):
        return result
    time.sleep(0.4)
    if not _append_required_action(
        result,
        {"kind": "wechat_open_target", **_key_code_macos(36)},
        status="keyboard_failed",
        error="Unable to open the WeChat target chat.",
    ):
        return result
    time.sleep(1.2)

    vision = DesktopVisionLayer(case_id=case_id, visible=True, hold_seconds=0.5)
    target_vision = vision.capture_and_ocr(
        label="wechat-target",
        expected_text=target,
        match_mode="all",
    )
    _append_vision_result(result, target_vision)

    verification = target_vision.get("verification") if isinstance(target_vision.get("verification"), dict) else {}
    if not target_vision.get("ok") or not verification.get("ok"):
        result.update({
            "status": "verification_failed",
            "error": "OCR could not verify the WeChat chat target. Message was not sent.",
            "verification_required": confirmation.get("verification_required"),
        })
        result["proof_manifest"] = write_proof_manifest(
            case_id=case_id,
            proofs=_screenshot_proofs(result),
        )
        return result

    clipboard = _set_clipboard(draft_message)
    result["desktop_actions"].append({"kind": "clipboard_set_message", **clipboard})
    if not clipboard.get("ok"):
        result.update({"status": "clipboard_failed", "error": clipboard.get("error")})
        return result

    if not _append_required_action(
        result,
        {"kind": "wechat_paste_message", **_keystroke_macos("v", command=True)},
        status="keyboard_failed",
        error="Unable to paste the WeChat message.",
    ):
        return result
    time.sleep(0.5)
    if not _append_required_action(
        result,
        {"kind": "wechat_send_message", **_key_code_macos(36)},
        status="keyboard_failed",
        error="Unable to send the WeChat message.",
    ):
        return result
    time.sleep(0.8)

    after_vision = vision.capture_and_ocr(
        label="wechat-sent",
        expected_text=target,
        match_mode="all",
    )
    _append_vision_result(result, after_vision)
    if not after_vision.get("ok"):
        result["proof_warning"] = after_vision.get("error") or "Post-send proof capture did not verify cleanly."

    result.update({
        "ok": True,
        "status": "sent" if not result.get("proof_warning") else "sent_with_proof_warning",
        "sent": True,
        "proof_manifest": write_proof_manifest(
            case_id=case_id,
            proofs=_screenshot_proofs(result),
        ),
    })
    return result
