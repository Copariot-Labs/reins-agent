from __future__ import annotations

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    result = {
        "ok": True,
        "worker": step.kind,
        "step_id": step.id,
        "input": state.message,
        "output": f"Processed: {state.message}",
    }

    state.scratch["last_backend_result"] = result
    return result


async def present_result(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    result = state.scratch.get("last_backend_result") or {
        "input": state.message,
        "output": f"Processed: {state.message}",
    }

    return {
        "ok": True,
        "worker": "result_present",
        "step_id": step.id,
        "presentation": result,
        "message": "Backend result recorded for operator review.",
    }


registry.register("backend_only", run)
registry.register("backend_process", run)
registry.register("result_present", present_result)
