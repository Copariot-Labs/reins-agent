from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from reins.features.presentation.models import (
    PresentationEngine,
    PresentationPlan,
    PresentationRequest,
    PresentationResult,
)


@dataclass(slots=True)
class EngineHealth:
    name: PresentationEngine
    available: bool
    message: str
    engine_path: Path | None = None
    python_path: Path | None = None


class PresentationEngineAdapter(ABC):
    name: PresentationEngine

    @abstractmethod
    def health(self) -> EngineHealth:
        """
        Check whether the engine and its required runtime are available.
        """

    @abstractmethod
    def render(
        self,
        *,
        request: PresentationRequest,
        plan: PresentationPlan,
        workspace: Path,
    ) -> PresentationResult:
        """
        Render a presentation inside the supplied workspace.
        """