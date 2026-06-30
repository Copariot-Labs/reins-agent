from __future__ import annotations

from typing import Any

from reins.features.workmode.desktop_vision import DesktopVisionLayer
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
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


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    metadata = dict(step.metadata or {})
    intake = state.scratch.get("intake", {})
    case_id = str(intake.get("case_id") or state.task_id)
    image_path = _first_metadata_value(metadata, "image_path", "path", "source")
    region = _first_metadata_value(metadata, "region", "rect", "crop")
    expected_text = _first_metadata_value(metadata, "expected_text", "contains", "verify_contains")
    visible = bool(step.visible_action and state.mode_policy.visible_actions)
    capture_desktop = _metadata_bool(metadata.get("capture_desktop"), default=not bool(image_path))
    label = str(metadata.get("label") or "ocr")
    match_mode = str(metadata.get("match_mode") or "all")
    language = metadata.get("language") or metadata.get("lang")
    config = metadata.get("config")

    if not image_path and not capture_desktop:
        return {
            "ok": False,
            "worker": "ocr",
            "step_id": step.id,
            "error": "No image_path provided in step.metadata and capture_desktop is disabled.",
        }

    vision = DesktopVisionLayer(
        case_id=case_id,
        visible=visible,
        hold_seconds=max(float(state.mode_policy.key_action_preview_ms or 0) / 1000, 0.2 if visible else 0),
    )

    if image_path:
        await state.emit_progress("Running OCR on provided image.", data={
            "worker": "ocr",
            "stage": "ocr.image.reading",
            "image_path": str(image_path),
            "expected_text": expected_text,
        })
        result = vision.ocr_image(
            str(image_path),
            label=label,
            region=region,
            expected_text=expected_text,
            match_mode=match_mode,
            language=str(language) if language else None,
            config=str(config) if config else None,
        )
    else:
        await state.emit_progress("Capturing desktop screenshot for OCR.", data={
            "worker": "ocr",
            "stage": "ocr.desktop.capturing",
            "expected_text": expected_text,
            "visible": visible,
        })
        result = vision.capture_and_ocr(
            label=label,
            region=region,
            expected_text=expected_text,
            match_mode=match_mode,
            language=str(language) if language else None,
            config=str(config) if config else None,
        )

    await state.emit_progress("OCR verification completed." if result.get("ok") else "OCR verification failed.", data={
        "worker": "ocr",
        "stage": "ocr.completed",
        "ok": bool(result.get("ok")),
        "verification": result.get("verification"),
        "error": result.get("error"),
    })

    context_update = {
        "extracted_text": result.get("text", ""),
        "ocr_verification": result.get("verification"),
    }

    return {
        "ok": bool(result.get("ok")),
        "worker": "ocr",
        "step_id": step.id,
        "ocr": result,
        "text": result.get("text", ""),
        "screenshots": result.get("screenshots") or [],
        "desktop_actions": result.get("actions") or [],
        "context": context_update,
    }


registry.register("ocr", run)
