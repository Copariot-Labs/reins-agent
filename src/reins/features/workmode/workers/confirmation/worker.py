from __future__ import annotations

from uuid import uuid4

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.policy import requires_confirmation
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    dispatch = state.scratch.get("pending_dispatch") or {}
    action = str(step.metadata.get("action") or dispatch.get("action") or "confirm_action")
    confirmation = {
        "id": dispatch.get("id") or str(uuid4()),
        "action": action,
        "channel": dispatch.get("channel") or step.metadata.get("channel") or "unknown",
        "target": dispatch.get("target") or step.metadata.get("target") or "operator-selected target",
        "title": step.title,
        "summary": "Operator approval is required before this action can continue.",
        "payload": {
            "message": dispatch.get("draft_message"),
        },
        "risk": dispatch.get("risk") or "consequential_action",
        "status": "pending",
        "source_step_id": dispatch.get("source_step_id") or step.id,
        "blocked_step_id": step.id,
        "requires_confirmation": requires_confirmation(action, {"external_submit": True}),
        "verification_required": dispatch.get("verification_required") or [
            "operator_confirmation",
        ],
    }
    state.scratch.setdefault("pending_confirmations", []).append(confirmation)

    return {
        "ok": True,
        "worker": "confirmation_gate",
        "step_id": step.id,
        "requires_confirmation": True,
        "status": "pending_confirmation",
        "blocked": True,
        "confirmation": confirmation,
        "message": "Confirmation required before continuing.",
    }


registry.register("confirmation_gate", run)
