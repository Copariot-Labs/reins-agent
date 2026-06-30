from __future__ import annotations

from typing import Any

from reins.features.workmode.desktop_vision import DesktopVisionLayer
from reins.features.workmode.desktop_window import DesktopWindowLayer, parse_rect
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.proof import write_proof_manifest
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


def _metadata_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _first_metadata_value(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _proofs_from_actions(actions: list[dict]) -> list[dict]:
    proofs = []
    for action in actions:
        screenshot = action.get("screenshot")
        if isinstance(screenshot, dict):
            proofs.append(screenshot)
        elif action.get("path"):
            proofs.append({
                "ok": bool(action.get("ok")),
                "kind": action.get("kind") or "proof",
                "path": str(action["path"]),
            })
    return proofs


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    intake = state.scratch.get("intake", {})
    case_id = intake.get("case_id") or state.task_id
    app_name = str(step.metadata.get("app_name") or "").strip()
    window_title = str(step.metadata.get("window_title") or step.metadata.get("title") or "").strip()
    target_path = str(step.metadata.get("path") or "").strip()
    target_url = str(step.metadata.get("url") or "").strip()
    role = str(step.metadata.get("role") or step.metadata.get("layout_role") or "default").strip() or "default"
    rect = parse_rect(step.metadata.get("rect"))
    region = _first_metadata_value(step.metadata, "region", "crop", "ocr_region")
    expected_text = _first_metadata_value(step.metadata, "expected_text", "contains", "verify_contains")
    should_ocr = _metadata_bool(step.metadata.get("ocr"), default=bool(expected_text))
    arrange = _metadata_bool(step.metadata.get("arrange"), default=True)
    focus_only = _metadata_bool(step.metadata.get("focus_only"), default=False)
    visible = bool(step.visible_action and state.mode_policy.visible_actions)
    hold_seconds = max(float(state.mode_policy.key_action_preview_ms or 0) / 1000, 0.35 if visible else 0)
    layer = DesktopWindowLayer(case_id=str(case_id), visible=visible, hold_seconds=hold_seconds)

    desktop_actions: list[dict] = [layer.capabilities()]
    await state.emit_progress("Preparing desktop window action.", data={
        "worker": "desktop_capture",
        "stage": "desktop.prepare",
        "app_name": app_name,
        "window_title": window_title,
        "target_path": target_path,
        "target_url": target_url,
        "visible": visible,
    })

    if target_url:
        await state.emit_progress("Opening URL in desktop browser.", data={
            "worker": "desktop_capture",
            "stage": "desktop.url.opening",
            "url": target_url,
        })
        desktop_actions.append(layer.open_url(target_url, proof_label="desktop-url-open"))
        if arrange:
            desktop_actions.append(layer.move_resize(rect=rect, title=target_url, role=role or "browser"))
    elif target_path:
        await state.emit_progress("Opening file or folder on desktop.", data={
            "worker": "desktop_capture",
            "stage": "desktop.path.opening",
            "path": target_path,
        })
        desktop_actions.append(layer.open_path(target_path, proof_label="desktop-path-open"))
        if arrange:
            desktop_actions.append(layer.move_resize(rect=rect, title=target_path, role=role))
    elif app_name:
        await state.emit_progress("Opening or focusing desktop application.", data={
            "worker": "desktop_capture",
            "stage": "desktop.app.opening",
            "app_name": app_name,
        })
        if focus_only:
            desktop_actions.append(layer.focus_app(app_name))
        else:
            desktop_actions.append(layer.open_app(app_name))
            desktop_actions.append(layer.focus_app(app_name))
        if arrange:
            desktop_actions.append(layer.move_resize(rect=rect, app_name=app_name, role=role))
    elif window_title:
        await state.emit_progress("Focusing desktop window.", data={
            "worker": "desktop_capture",
            "stage": "desktop.window.focusing",
            "window_title": window_title,
        })
        desktop_actions.append(layer.focus_window(window_title))
        if arrange:
            desktop_actions.append(layer.move_resize(rect=rect, title=window_title, role=role))

    await state.emit_progress("Capturing desktop proof.", data={
        "worker": "desktop_capture",
        "stage": "desktop.proof.capturing",
    })
    state_snapshot = layer.snapshot_state(proof_label="desktop-final")
    desktop_actions.extend(state_snapshot.get("actions", []))

    screenshots = layer.collect_screenshots(desktop_actions)
    ocr_result: dict[str, Any] | None = None

    if should_ocr:
        await state.emit_progress("Running desktop OCR verification.", data={
            "worker": "desktop_capture",
            "stage": "desktop.ocr.verifying",
            "expected_text": expected_text,
        })
        vision = DesktopVisionLayer(case_id=str(case_id), visible=visible, hold_seconds=0.2 if visible else 0)
        if screenshots:
            ocr_result = vision.ocr_image(
                screenshots[-1],
                label="desktop-verification",
                region=region,
                expected_text=expected_text,
                match_mode=str(step.metadata.get("match_mode") or "all"),
            )
        else:
            ocr_result = vision.capture_and_ocr(
                label="desktop-verification",
                region=region,
                expected_text=expected_text,
                match_mode=str(step.metadata.get("match_mode") or "all"),
            )
        desktop_actions.extend(ocr_result.get("actions") or [])
        screenshots.extend(str(path) for path in ocr_result.get("screenshots") or [] if path)
        screenshots = list(dict.fromkeys(screenshots))

    hard_failures = [
        action for action in desktop_actions
        if action.get("ok") is False and action.get("kind") in {
            "desktop_app_open",
            "desktop_path_open",
            "desktop_url_open",
            "desktop_app_focus",
            "desktop_window_focus",
        }
    ]
    ok = not hard_failures and bool(screenshots or any(action.get("ok") for action in desktop_actions))
    if expected_text:
        ok = ok and bool(ocr_result and ocr_result.get("ok"))

    proofs = _proofs_from_actions(desktop_actions)
    manifest = write_proof_manifest(
        case_id=str(case_id),
        proofs=proofs,
    )

    return {
        "ok": ok,
        "worker": "desktop_capture",
        "step_id": step.id,
        "message": "Desktop window action proof captured." if ok else "Desktop window action failed.",
        "screenshots": screenshots,
        "desktop_actions": desktop_actions,
        "desktop": {
            "kind": "desktop_window_state",
            "platform": layer.platform,
            "visible": visible,
            "app_name": app_name,
            "window_title": window_title,
            "target_path": target_path,
            "target_url": target_url,
            "screenshots": screenshots,
            "state": state_snapshot,
            "verification": ocr_result.get("verification") if ocr_result else None,
        },
        "ocr": ocr_result,
        "proofs": proofs,
        "proof_manifest": manifest,
    }


registry.register("desktop_capture", run)
