from __future__ import annotations

import os
from pathlib import Path


def default_reins_home() -> Path:
    return Path.home() / ".reins"


def default_hermes_home() -> Path:
    return Path.home() / ".hermes"


def get_reins_home() -> Path:
    value = os.environ.get("REINS_HOME")

    if value:
        return Path(value).expanduser().resolve()

    return default_reins_home().resolve()


def get_hermes_home() -> Path:
    value = os.environ.get("HERMES_HOME")

    if value:
        return Path(value).expanduser().resolve()

    return default_hermes_home().resolve()


def ensure_reins_home() -> Path:
    reins_home = get_reins_home()
    reins_home.mkdir(parents=True, exist_ok=True)
    return reins_home


def migration_marker_path(reins_home: Path | None = None) -> Path:
    if reins_home is None:
        reins_home = get_reins_home()

    return reins_home / ".migrated-from-hermes"
