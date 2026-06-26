from __future__ import annotations

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.workers.ocr.engine import extract_text_from_image
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    image_path = step.metadata.get("image_path")

    if not image_path:
        return {
            "ok": False,
            "worker": "ocr",
            "step_id": step.id,
            "error": "No image_path provided in step.metadata.",
        }

    result = extract_text_from_image(str(image_path))
    context_update = {
        "extracted_text": result.get("text", "")
    }

    return {
        "ok": bool(result.get("ok")),
        "worker": "ocr",
        "step_id": step.id,
        "ocr": result,
        "text": result.get("text", ""),
        "context": context_update,
    }


registry.register("ocr", run)
