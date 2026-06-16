from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import json


EventType = Literal[
    "task_started",
    "step_started",
    "step_finished",
    "browser_action",
    "desktop_action",
    "artifact_created",
    "source_opened",
    "confirmation_required",
    "task_failed",
    "task_finished",
]


@dataclass
class WorkEvent:
    type: EventType
    message: str
    task_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_sse(self) -> str:
        return f"data: {self.to_json()}\n\n"