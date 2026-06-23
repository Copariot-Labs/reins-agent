from __future__ import annotations

from typing import Any

from reins.features.workmode.planner import WorkPlan, WorkStep
from reins.features.workmode.vendor_hermes import call_vendor_hermes_planner


class HermesPlannerError(Exception):
    pass


ALLOWED_STEP_KINDS = {
    "backend_only",
    "office_generate",
}


def _make_step(raw: dict[str, Any]) -> WorkStep:
    if not isinstance(raw, dict):
        raise HermesPlannerError("Hermes step must be a JSON object.")

    kind = str(raw.get("kind") or "backend_only")

    if kind not in ALLOWED_STEP_KINDS:
        raise HermesPlannerError(f"Unsupported Hermes step kind: {kind}")

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


def _validate_plan_dict(raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        raise HermesPlannerError("Hermes planner output is not a JSON object.")

    steps = raw.get("steps")

    if not isinstance(steps, list):
        raise HermesPlannerError("Hermes planner steps must be a list.")

    if not steps:
        raise HermesPlannerError("Hermes planner output has no steps.")

    for step in steps:
        if not isinstance(step, dict):
            raise HermesPlannerError("Each Hermes step must be a JSON object.")

        kind = str(step.get("kind") or "backend_only")

        if kind not in ALLOWED_STEP_KINDS:
            raise HermesPlannerError(f"Unsupported Hermes step kind: {kind}")


def build_plan_from_hermes_dict(
    raw: dict[str, Any],
    *,
    message: str,
    policy,
    path,
) -> WorkPlan:
    _validate_plan_dict(raw)

    steps = [_make_step(step) for step in raw["steps"]]

    return WorkPlan(
        id=str(raw.get("id") or raw.get("plan_id") or "hermes-plan"),
        intent=str(raw.get("intent") or message),
        execution_path=path,
        mode=policy.mode,
        summary_for_user=str(
            raw.get("summary_for_user")
            or raw.get("summary")
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
    """
    Safe Hermes planner wrapper.

    This must never crash WorkMode.

    Returns:
    - (WorkPlan, None) if Hermes succeeds
    - (None, error_dict) if Hermes fails
    """

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