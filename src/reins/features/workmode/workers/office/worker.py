from __future__ import annotations

from reins.features.workmode.artifacts import generate_office_artifact, infer_office_artifact_format
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.presentation import present_file
from reins.features.workmode.workers.office.content_writer import generate_office_content
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    intake = state.scratch.get("intake", {})
    intake = intake if isinstance(intake, dict) else {}

    try:
        await state.emit_progress(
            "Writing Office document content.",
            data={
                "worker": "office_generate",
                "stage": "office.content_writing",
                "step_id": step.id,
                "step_title": step.title,
            },
        )

        content = generate_office_content(step, state)

        title = str(content.get("title") or "WorkMode Document").strip()
        body = str(content.get("body") or state.message).strip()
        artifact_format = infer_office_artifact_format(
            state.message,
            content.get("artifact_format"),
            step.metadata,
            step.expected_artifacts,
            step.title,
            step.description,
        )

        await state.emit_progress(
            "Generating Office artifact.",
            data={
                "worker": "office_generate",
                "stage": "office.generating",
                "title": title,
                "artifact_format": artifact_format,
                "document_kind": content.get("document_kind"),
                "content_writer": content.get("writer"),
                "uses_sources": bool(state.sources),
                "uses_research_context": bool(state.scratch.get("research_summary")),
            },
        )

        path = generate_office_artifact(artifact_format, title, body, content)

    except Exception as exc:
        return {
            "ok": False,
            "worker": "office_generate",
            "step_id": step.id,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    artifact = {
        "kind": artifact_format,
        "type": artifact_format,
        "artifact_format": artifact_format,
        "title": title,
        "path": str(path),
        "summary": f"Generated Office {artifact_format.upper()} artifact: {path.name}",
        "case_id": intake.get("case_id") or state.task_id,
        "issue_type": intake.get("issue_type"),
        "priority": intake.get("priority"),
        "location": intake.get("location"),
        "workflow": intake.get("workflow"),
        "content": body,
        "sheets": content.get("sheets") if isinstance(content.get("sheets"), list) else [],
        "slides": content.get("slides") if isinstance(content.get("slides"), list) else [],
        "source_count": len(state.sources),
        "artifact_count_before_generation": len(state.artifacts),
        "metadata": {
            "step_id": step.id,
            "step_title": step.title,
            "worker": "office_generate",
            "planner_metadata": step.metadata,
            "artifact_format": artifact_format,
            "document_kind": content.get("document_kind"),
            "missing_fields": content.get("missing_fields", []),
            "content_writer": content.get("writer"),
            "writer_error": content.get("writer_error"),
            "uses_sources": bool(state.sources),
            "uses_research_context": bool(state.scratch.get("research_summary")),
        },
    }

    await state.emit_progress(
        "Office artifact generated.",
        data={
            "worker": "office_generate",
            "stage": "office.generated",
            "path": str(path),
            "title": title,
            "artifact_format": artifact_format,
            "document_kind": content.get("document_kind"),
            "content_writer": content.get("writer"),
            "source_count": len(state.sources),
        },
    )

    return {
        "ok": True,
        "worker": "office_generate",
        "step_id": step.id,
        "artifact": artifact,
        "context": {
            "latest_office_artifact_path": str(path),
            "latest_office_artifact_title": title,
            "latest_office_artifact_format": artifact_format,
            "latest_office_document_kind": content.get("document_kind"),
        },
    }


async def present_artifact(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    artifact_kind = step.metadata.get("artifact_kind")
    artifact = state.latest_artifact(str(artifact_kind)) if artifact_kind else None
    if artifact is None:
        artifact = state.latest_artifact()

    if artifact is None:
        return {
            "ok": False,
            "worker": "artifact_present",
            "step_id": step.id,
            "error": "No artifact is available to present.",
        }

    visible = bool(step.visible_action and state.mode_policy.visible_actions)

    await state.emit_progress(
        "Preparing artifact presentation.",
        data={
            "worker": "artifact_present",
            "stage": "office.present.prepare",
            "artifact_kind": artifact.get("kind"),
            "path": artifact.get("path"),
            "visible": visible,
        },
    )

    result: WorkerResult = {
        "ok": True,
        "worker": "artifact_present",
        "step_id": step.id,
        "artifact": artifact,
        "message": "Artifact recorded for operator verification.",
    }

    if visible and artifact.get("path"):
        await state.emit_progress(
            "Opening Office artifact for verification.",
            data={
                "worker": "artifact_present",
                "stage": "office.present.opening",
                "path": artifact.get("path"),
            },
        )

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

        await state.emit_progress(
            result["message"],
            data={
                "worker": "artifact_present",
                "stage": "office.present.completed",
                "ok": bool(action.get("ok")),
                "screenshot": action.get("screenshot"),
                "error": action.get("error"),
                "action": action,
            },
        )

    return result


registry.register("office_generate", run)
registry.register("artifact_present", present_artifact)
