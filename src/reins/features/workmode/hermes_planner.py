from __future__ import annotations

from typing import Any

from reins.features.workmode.desktop_resolver import infer_desktop_app_name, is_desktop_app_intent
from reins.features.workmode.planner import WorkPlan, WorkStep
from reins.features.workmode.router import ExecutionPath
from reins.features.workmode.url_resolver import infer_url_from_message, is_browser_intent
from reins.features.workmode.vendor_hermes import call_vendor_hermes_planner

# 🔥 NEW: strict contract
from reins.features.workmode.runtime.execution_contract import ExecutionContract


class HermesPlannerError(Exception):
    pass


ALLOWED_STEP_KINDS = {
    "backend_only",
    "backend_process",
    "result_present",
    "office_generate",
    "artifact_present",
    "browser_source",
    "desktop_capture",
    "ocr",
    "wechat_prepare",
    "confirmation_gate",
}


def normalize_kind(raw: dict[str, Any]) -> str:
    """
    Deterministic intent normalization (NO heuristics here anymore).
    Hermes must be trusted minimally.
    """

    kind = str(raw.get("kind") or "backend_only").lower()

    # Only lightweight normalization (NO routing logic here)
    if kind not in ALLOWED_STEP_KINDS:
        kind = "backend_only"

    return kind


def _make_step(raw: dict[str, Any]) -> WorkStep:
    if not isinstance(raw, dict):
        raise HermesPlannerError("Hermes step must be a JSON object.")

    kind = normalize_kind(raw)

    # 🚨 STRICT VALIDATION (P7.9.0.5)
    ExecutionContract.validate(kind)

    return WorkStep(
        id=str(raw.get("id") or kind),
        kind=kind,
        title=str(raw.get("title") or "Untitled step"),
        worker=str(raw.get("worker") or "workmode.backend"),
        description=str(raw.get("description") or ""),
        visible_action=bool(raw.get("visible_action", False)),
        requires_confirmation=bool(raw.get("requires_confirmation", False)),
        expected_artifacts=list(raw.get("expected_artifacts") or []),
        depends_on=list(raw.get("depends_on") or []),
        metadata=dict(raw.get("metadata") or {}),
    )


def _path_value(path: Any) -> str:
    return path.value if isinstance(path, ExecutionPath) else str(path)


def _is_browser_path(path: Any) -> bool:
    return path == ExecutionPath.BROWSER or _path_value(path) == ExecutionPath.BROWSER.value


def _is_desktop_path(path: Any) -> bool:
    return path == ExecutionPath.DESKTOP or _path_value(path) == ExecutionPath.DESKTOP.value


def _step_text(step: WorkStep) -> str:
    return " ".join([
        step.kind,
        step.title,
        step.worker,
        step.description,
        " ".join(str(value) for value in step.metadata.values()),
    ])


def _repair_steps(
    steps: list[WorkStep],
    *,
    message: str,
    policy,
    path,
) -> list[WorkStep]:
    should_be_browser = _is_browser_path(path) or is_browser_intent(message) or any(
        is_browser_intent(_step_text(step)) for step in steps
    )

    if not should_be_browser:
        should_be_desktop = _is_desktop_path(path) or is_desktop_app_intent(message) or any(
            is_desktop_app_intent(_step_text(step)) for step in steps
        )

        if not should_be_desktop:
            return steps

        app_name = infer_desktop_app_name(message)
        for step in steps:
            if step.kind == "desktop_capture":
                metadata = dict(step.metadata)
                if app_name and not metadata.get("app_name"):
                    metadata["app_name"] = app_name
                return [
                    WorkStep(
                        id=step.id,
                        kind="desktop_capture",
                        title=step.title or "Capture desktop evidence",
                        worker="workmode.desktop",
                        description=step.description or "Open or capture desktop evidence for operator verification.",
                        visible_action=policy.visible_actions,
                        requires_confirmation=False,
                        expected_artifacts=step.expected_artifacts or ["screenshot"],
                        depends_on=step.depends_on,
                        metadata=metadata,
                    )
                ]

        return [
            WorkStep(
                id="desktop-capture",
                kind="desktop_capture",
                title=f"Open {app_name} and capture proof" if app_name else "Capture desktop evidence",
                worker="workmode.desktop",
                description="Open or capture the requested desktop state for operator verification.",
                visible_action=policy.visible_actions,
                expected_artifacts=["screenshot"],
                metadata={"app_name": app_name} if app_name else {},
            )
        ]

    url = infer_url_from_message(message)
    for step in steps:
        if step.kind == "browser_source":
            metadata = dict(step.metadata)
            if url and not metadata.get("url"):
                metadata["url"] = url
            return [
                WorkStep(
                    id=step.id,
                    kind="browser_source",
                    title=step.title or "Open browser evidence",
                    worker="workmode.browser",
                    description=step.description or "Open a browser source for operator verification.",
                    visible_action=policy.visible_actions,
                    requires_confirmation=False,
                    expected_artifacts=step.expected_artifacts,
                    depends_on=step.depends_on,
                    metadata=metadata,
                )
            ]

    return [
        WorkStep(
            id="browser-source",
            kind="browser_source",
            title="Open browser evidence",
            worker="workmode.browser",
            description="Open the requested website and save browser evidence for verification.",
            visible_action=policy.visible_actions,
            metadata={"url": url} if url else {},
        )
    ]


def _validate_plan_dict(raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        raise HermesPlannerError("Hermes planner output is not a JSON object.")

    steps = raw.get("steps")

    if not isinstance(steps, list) or not steps:
        raise HermesPlannerError("Hermes planner steps must be a non-empty list.")

    for step in steps:
        if not isinstance(step, dict):
            raise HermesPlannerError("Each Hermes step must be a JSON object.")


def build_plan_from_hermes_dict(
    raw: dict[str, Any],
    *,
    message: str,
    policy,
    path,
) -> WorkPlan:

    _validate_plan_dict(raw)

    steps = _repair_steps(
        [_make_step(step) for step in raw["steps"]],
        message=message,
        policy=policy,
        path=path,
    )

    return WorkPlan(
        id=str(raw.get("id") or raw.get("plan_id") or "hermes-plan"),
        intent=str(raw.get("intent") or message),
        execution_path=_path_value(path),
        mode=policy.mode,
        summary_for_user=str(
            raw.get("summary_for_user")
            or "Hermes generated a WorkMode plan."
        ),
        steps=steps,
        risk_flags=list(raw.get("risk_flags") or []),
        planner="hermes",
        version=int(raw.get("version") or 1),
    )


def try_build_hermes_plan(
    message: str,
    *,
    policy,
    path,
    intake: dict[str, Any] | None = None,
) -> tuple[WorkPlan | None, dict[str, Any] | None]:

    try:
        raw = call_vendor_hermes_planner(
            message,
            mode=policy.mode,
            intake=intake,
        )

        plan = build_plan_from_hermes_dict(
            raw,
            message=message,
            policy=policy,
            path=path,
        )

        return plan, None

    except Exception as exc:
        return None, {
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
