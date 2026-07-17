from __future__ import annotations

from dataclasses import asdict
from typing import Any

from reins.features.presentation.engine_registry import (
    create_engine_registry,
)


def run_presentation_doctor() -> dict[str, Any]:
    registry = create_engine_registry()

    engines: list[dict[str, Any]] = []

    for engine in registry.values():
        health = engine.health()
        data = asdict(health)

        data["name"] = health.name.value

        if health.engine_path is not None:
            data["engine_path"] = str(health.engine_path)

        if health.python_path is not None:
            data["python_path"] = str(health.python_path)

        engines.append(data)

    return {
        "ok": all(engine["available"] for engine in engines),
        "engines": engines,
    }