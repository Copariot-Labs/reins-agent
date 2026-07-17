from __future__ import annotations

from reins.features.presentation.engines import (
    FrontendSlidesEngine,
    NativePptxEngine,
    PptMasterEngine,
    PresentationEngineAdapter,
)
from reins.features.presentation.models import PresentationEngine


def create_engine_registry() -> dict[
    PresentationEngine,
    PresentationEngineAdapter,
]:
    engines: list[PresentationEngineAdapter] = [
        PptMasterEngine(),
        FrontendSlidesEngine(),
        NativePptxEngine(),
    ]

    return {
        engine.name: engine
        for engine in engines
    }


def get_engine(
    name: PresentationEngine,
) -> PresentationEngineAdapter:
    registry = create_engine_registry()

    try:
        return registry[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown presentation engine: {name.value}"
        ) from exc