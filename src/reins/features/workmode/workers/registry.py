from __future__ import annotations

import importlib
from typing import Any

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.workers.types import WorkerFn, WorkerResult


class WorkModeWorkerError(Exception):
    pass


class WorkerRegistry:
    def __init__(self) -> None:
        self._workers: dict[str, WorkerFn] = {}
        self._loaded_modules: set[str] = set()

    def register(self, kind: str, worker: WorkerFn) -> None:
        self._workers[kind] = worker

    def has(self, kind: str) -> bool:
        return kind in self._workers

    def get(self, kind: str) -> WorkerFn:
        worker = self._workers.get(kind)

        if worker is None:
            raise WorkModeWorkerError(f"No worker registered for step kind: {kind}")

        return worker

    def load_module(self, module_path: str) -> None:
        if module_path in self._loaded_modules:
            return

        importlib.import_module(module_path)
        self._loaded_modules.add(module_path)

    def load_defaults(self) -> None:
        modules = [
            "reins.features.workmode.workers.backend.worker",
            "reins.features.workmode.workers.office.worker",
            "reins.features.workmode.workers.desktop.worker",
            "reins.features.workmode.workers.browser.worker",
            "reins.features.workmode.workers.ocr.worker",
            "reins.features.workmode.workers.wechat.worker",
            "reins.features.workmode.workers.confirmation.worker",
        ]

        for module in modules:
            self.load_module(module)

    async def run(self, step: WorkStep, state: WorkExecutionState) -> WorkerResult:
        self.load_defaults()

        worker = self.get(step.kind)
        return await worker(step, state)


registry = WorkerRegistry()


async def run_worker(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    return await registry.run(step, state)