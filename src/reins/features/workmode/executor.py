from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reins.features.workmode.policy import ModePolicy


@dataclass
class WorkExecutionState:
    task_id: str
    message: str
    mode_policy: ModePolicy
    plan_id: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    step_status: dict[str, str] = field(default_factory=dict)
    scratch: dict[str, Any] = field(default_factory=dict)

    def add_artifact(self, artifact: dict[str, Any]) -> None:
        self.artifacts.append(dict(artifact))

    def add_source(self, source: dict[str, Any]) -> None:
        self.sources.append(dict(source))

    def latest_artifact(self, kind: str | None = None) -> dict[str, Any] | None:
        for artifact in reversed(self.artifacts):
            if kind is None or artifact.get("kind") == kind:
                return artifact

        return None
