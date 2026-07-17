from __future__ import annotations

import os
from pathlib import Path
from typing import Any


REINS_ROOT = Path(__file__).resolve().parents[4]
EXTERNAL_ROOT = REINS_ROOT / "external"


def get_reins_home() -> Path:
    configured_home = os.environ.get("REINS_HOME")

    if configured_home:
        return Path(configured_home).expanduser().resolve()

    return Path.home() / ".reins"


def get_presentations_home() -> Path:
    configured_home = os.environ.get("REINS_PRESENTATIONS_HOME")

    if configured_home:
        return Path(configured_home).expanduser().resolve()

    return get_reins_home() / "presentations"


PRESENTATION_CONFIG: dict[str, dict[str, Path]] = {
    "ppt_master": {
        "path": EXTERNAL_ROOT / "ppt-master",
        "venv": EXTERNAL_ROOT / ".venvs" / "ppt-master",
    },
    "frontend_slides": {
        "path": EXTERNAL_ROOT / "frontend-slides",
        "venv": EXTERNAL_ROOT / ".venvs" / "frontend-slides",
    },
}


def get_engine_config(name: str) -> dict[str, Path]:
    try:
        return PRESENTATION_CONFIG[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown presentation engine configuration: {name}"
        ) from exc


def get_engine_path(name: str) -> Path:
    return get_engine_config(name)["path"]


def get_presentation_settings() -> dict[str, Any]:
    return {
        "reins_root": str(REINS_ROOT),
        "external_root": str(EXTERNAL_ROOT),
        "reins_home": str(get_reins_home()),
        "presentations_home": str(get_presentations_home()),
        "engines": {
            name: {
                key: str(value)
                for key, value in config.items()
            }
            for name, config in PRESENTATION_CONFIG.items()
        },
    }