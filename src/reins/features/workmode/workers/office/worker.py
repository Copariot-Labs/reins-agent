from __future__ import annotations

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.artifacts import generate_demo_docx
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.presentation import present_file
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    intake = state.scratch.get("intake", {})
    title = "Resident Case Report"
    body = state.message

    try:
        path = generate_demo_docx(title, body)
    except Exception as exc:
        return {
            "ok": False,
            "worker": "office_generate",
            "step_id": step.id,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    artifact = {
        "kind": "docx",
        "type": "docx",
        "title": title,
        "path": str(path),
        "summary": f"Generated Word report: {path.name}",
        "case_id": intake.get("case_id"),
        "issue_type": intake.get("issue_type"),
        "priority": intake.get("priority"),
        "location": intake.get("location"),
        "workflow": intake.get("workflow"),
        "content": body,
        "metadata": {
            "step_id": step.id,
            "step_title": step.title,
            "worker": "office_generate",
            "planner_metadata": step.metadata,
        },
    }

    return {
        "ok": True,
        "worker": "office_generate",
        "step_id": step.id,
        "artifact": artifact,
    }


async def present_artifact(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    artifact_kind = step.metadata.get("artifact_kind")
    artifact = state.latest_artifact(str(artifact_kind)) if artifact_kind else state.latest_artifact()

    if artifact is None:
        return {
            "ok": False,
            "worker": "artifact_present",
            "step_id": step.id,
            "error": "No artifact is available to present.",
        }

    result: WorkerResult = {
        "ok": True,
        "worker": "artifact_present",
        "step_id": step.id,
        "artifact": artifact,
        "message": "Artifact recorded for operator verification.",
    }

    if step.visible_action and state.mode_policy.visible_actions and artifact.get("path"):
        action = present_file(
            case_id=str(artifact.get("case_id") or state.task_id),
            path=str(artifact["path"]),
            title=str(artifact.get("title") or artifact.get("kind") or "WorkMode artifact"),
            hold_seconds=max(state.mode_policy.key_action_preview_ms / 1000, 1.5),
        )
        result["desktop_actions"] = [action]
        screenshot = action.get("screenshot")
        if isinstance(screenshot, dict) and screenshot.get("ok") and screenshot.get("path"):
            result["screenshots"] = [str(screenshot["path"])]
        result["message"] = (
            "Artifact opened for operator verification."
            if action.get("ok")
            else "Artifact recorded; visible opening was not available."
        )

    return result


registry.register("office_generate", run)
registry.register("artifact_present", present_artifact)
