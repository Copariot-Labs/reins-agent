from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reins.features.workmode.policy import ModePolicy
from reins.features.workmode.runtime.observation import Observation


@dataclass
class WorkExecutionState:
    task_id: str
    message: str
    mode_policy: ModePolicy
    plan_id: str

    # EXISTING MEMORY
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    step_status: dict[str, str] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)

    # ADDITION
    observations: list[Observation] = field(default_factory=list)
    browser_session: Any = None
    desktop_session: Any = None
    progress_queue: Any = None
    current_step_id: str | None = None
    current_step_kind: str | None = None

    # ARTIFACT HANDLERS
    def add_artifact(self, artifact: dict[str, Any]) -> None:
        self.artifacts.append(dict(artifact))

    def add_source(self, source: dict[str, Any]) -> None:
        self.sources.append(dict(source))

    def add_observation(self, obs: Observation) -> None:
        """
        Central memory tracking
        """
        self.observations.append(obs)

    def latest_artifact(self, kind: str | None = None) -> dict[str, Any] | None:
        for artifact in reversed(self.artifacts):
            if kind is None or artifact.get("kind") == kind:
                return artifact
        return None

    async def emit_progress(
        self,
        message: str,
        *,
        event_type: str = "work.step.progress",
        data: dict[str, Any] | None = None,
    ) -> None:
        if self.progress_queue is None:
            return
        payload = {
            "type": event_type,
            "message": message,
            "data": dict(data or {}),
        }
        await self.progress_queue.put(payload)
