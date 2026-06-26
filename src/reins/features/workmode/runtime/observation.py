from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional
from datetime import datetime, timezone


@dataclass
class Observation:
    """
    Execution memory unit.

    Every step in WorkMode becomes a structured observation.
    This enables:
    - replay
    - debugging
    - UI visualization
    - agent memory
    """

    step_id: str
    kind: str

    input: Any
    output: Any

    screenshots: list[str] = None
    browser_state: Optional[dict[str, Any]] = None
    desktop_state: Optional[dict[str, Any]] = None

    timestamp: str = None

    def __post_init__(self):
        if self.screenshots is None:
            self.screenshots = []

        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """
        Convert observation into JSON-safe structure.
        """
        return {
            "step_id": self.step_id,
            "kind": self.kind,
            "input": self.input,
            "output": self.output,
            "screenshots": self.screenshots,
            "browser_state": self.browser_state,
            "desktop_state": self.desktop_state,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Observation":
        return Observation(
            step_id=data.get("step_id"),
            kind=data.get("kind"),
            input=data.get("input"),
            output=data.get("output"),
            screenshots=data.get("screenshots", []),
            browser_state=data.get("browser_state"),
            desktop_state=data.get("desktop_state"),
            timestamp=data.get("timestamp"),
        )