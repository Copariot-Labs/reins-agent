from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from typing import Any

from reins.features.workmode.planner import WorkPlan, WorkStep


class HermesPlannerError(Exception):
    pass


def _make_step(raw: dict[str, Any]) -> WorkStep:
    return WorkStep(
        id=str(raw.get("id") or raw.get("kind") or "step"),
        kind=str(raw.get("kind") or "backend_only"),
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

    if not raw.get("steps"):
        raise HermesPlannerError("Hermes planner output has no steps.")

    if not isinstance(raw["steps"], list):
        raise HermesPlannerError("Hermes planner steps must be a list.")


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
            or "Hermes generated a plan."
        ),
        steps=steps,
        risk_flags=list(raw.get("risk_flags") or []),
        planner="hermes",
        version=int(raw.get("version") or 1),
    )


def call_hermes_planner(message: str, *, mode: str) -> dict[str, Any]:
    """
    Calls Hermes planner if REINS_HERMES_PLANNER_CMD is configured.

    Example env:
    REINS_HERMES_PLANNER_CMD="python -m reins.vendor.hermes_planner"
    """

    cmd = os.environ.get("REINS_HERMES_PLANNER_CMD")

    if not cmd:
        raise HermesPlannerError("REINS_HERMES_PLANNER_CMD is not configured.")

    payload = {
        "message": message,
        "mode": mode,
    }

    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        text=True,
        shell=True,
        capture_output=True,
        timeout=30,
    )

    if proc.returncode != 0:
        raise HermesPlannerError(
            f"Hermes planner failed with exit code {proc.returncode}: {proc.stderr}"
        )

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HermesPlannerError(f"Hermes planner returned invalid JSON: {exc}") from exc


def try_build_hermes_plan(
    message: str,
    *,
    policy,
    path,
) -> tuple[WorkPlan | None, dict[str, Any] | None]:
    """
    Safe Hermes planner wrapper.

    Returns:
    - (WorkPlan, None) if Hermes succeeds
    - (None, error_dict) if Hermes fails

    This must never crash WorkMode.
    """

    try:
        raw = call_hermes_planner(message, mode=policy.mode)

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