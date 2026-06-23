from __future__ import annotations

from typing import Any, Awaitable, Callable

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep


WorkerResult = dict[str, Any]
WorkerFn = Callable[[WorkStep, WorkExecutionState], Awaitable[WorkerResult]]


class WorkModeWorkerError(Exception):
    pass


# BACKEND WORKER
async def backend_only_worker(
    step: WorkStep,
    state: WorkExecutionState,
) -> WorkerResult:
    return {
        "ok": True,
        "worker": "backend_only",
        "step_id": step.id,
        "input": state.message,
        "output": f"Processed: {state.message}",
    }


# OFFICE WORKER
async def office_generate_worker(
    step: WorkStep,
    state: WorkExecutionState,
) -> WorkerResult:
    intake = state.scratch.get("intake", {})

    artifact = {
        "type": "docx",
        "title": "Resident Case Report",
        "case_id": intake.get("case_id"),
        "issue_type": intake.get("issue_type"),
        "priority": intake.get("priority"),
        "location": intake.get("location"),
        "workflow": intake.get("workflow"),
        "content": state.message,
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


# BROWSER SOURCE WORKER PLACEHOLDER
async def browser_source_worker(
    step: WorkStep,
    state: WorkExecutionState,
) -> WorkerResult:
    return {
        "ok": True,
        "worker": "browser_source",
        "step_id": step.id,
        "sources": [],
        "message": "Browser source worker placeholder. Real browser automation comes in P7/P8.",
    }


# DESKTOP CAPTURE WORKER PLACEHOLDER
async def desktop_capture_worker(
    step: WorkStep,
    state: WorkExecutionState,
) -> WorkerResult:
    return {
        "ok": True,
        "worker": "desktop_capture",
        "step_id": step.id,
        "screenshots": [],
        "message": "Desktop capture worker placeholder. Real computer-use comes in P7.",
    }


# WECHAT PREPARE WORKER PLACEHOLDER
async def wechat_prepare_worker(
    step: WorkStep,
    state: WorkExecutionState,
) -> WorkerResult:
    intake = state.scratch.get("intake", {})

    draft_message = (
        f"Resident issue update:\n"
        f"- Case ID: {intake.get('case_id')}\n"
        f"- Issue type: {intake.get('issue_type')}\n"
        f"- Priority: {intake.get('priority')}\n"
        f"- Location: {intake.get('location')}\n"
        f"- Description: {state.message}"
    )

    return {
        "ok": True,
        "worker": "wechat_prepare",
        "step_id": step.id,
        "requires_confirmation": True,
        "draft_message": draft_message,
        "message": "WeChat message prepared. Sending requires confirmation.",
    }


# CONFIRMATION GATE WORKER PLACEHOLDER
async def confirmation_gate_worker(
    step: WorkStep,
    state: WorkExecutionState,
) -> WorkerResult:
    return {
        "ok": True,
        "worker": "confirmation_gate",
        "step_id": step.id,
        "requires_confirmation": True,
        "message": "Confirmation required before continuing.",
    }


# WORKER REGISTRY
WORKER_REGISTRY: dict[str, WorkerFn] = {
    "backend_only": backend_only_worker,
    "office_generate": office_generate_worker,
    "browser_source": browser_source_worker,
    "desktop_capture": desktop_capture_worker,
    "wechat_prepare": wechat_prepare_worker,
    "confirmation_gate": confirmation_gate_worker,
}


async def run_worker(
    step: WorkStep,
    state: WorkExecutionState,
) -> WorkerResult:
    worker = WORKER_REGISTRY.get(step.kind)

    if worker is None:
        raise WorkModeWorkerError(f"No worker registered for step kind: {step.kind}")

    return await worker(step, state)