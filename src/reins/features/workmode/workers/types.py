from __future__ import annotations

from typing import Any, Awaitable, Callable

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep


WorkerResult = dict[str, Any]
WorkerFn = Callable[[WorkStep, WorkExecutionState], Awaitable[WorkerResult]]