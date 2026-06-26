from __future__ import annotations

import re
from uuid import uuid4

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


def _guess_target(message: str) -> str:
    match = re.search(r"\bto\s+(.+?)(?:\s+about\b|$)", message, flags=re.IGNORECASE)
    if match:
        target = match.group(1).strip(" .,:;")
        if target:
            return target
    return "WeChat contact"


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    intake = state.scratch.get("intake", {})
    target = str(step.metadata.get("target") or _guess_target(state.message))

    draft_message = (
        "Resident issue update:\n"
        f"- Case ID: {intake.get('case_id')}\n"
        f"- Issue type: {intake.get('issue_type')}\n"
        f"- Priority: {intake.get('priority')}\n"
        f"- Location: {intake.get('location')}\n"
        f"- Description: {state.message}"
    )
    dispatch = {
        "id": str(uuid4()),
        "action": "send_message",
        "channel": "wechat",
        "target": target,
        "draft_message": draft_message,
        "case_id": intake.get("case_id"),
        "issue_type": intake.get("issue_type"),
        "priority": intake.get("priority"),
        "location": intake.get("location"),
        "risk": "external_message",
        "status": "drafted",
        "source_step_id": step.id,
        "verification_required": ["operator_confirmation", "ocr_chat_title_before_send"],
    }
    state.scratch["pending_dispatch"] = dispatch

    return {
        "ok": True,
        "worker": "wechat_prepare",
        "step_id": step.id,
        "requires_confirmation": True,
        "dispatch": dispatch,
        "draft_message": draft_message,
        "message": "WeChat message prepared. Sending requires confirmation.",
    }


registry.register("wechat_prepare", run)
