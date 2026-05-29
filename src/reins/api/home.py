from __future__ import annotations

from pathlib import Path

from reins.compat.paths import get_reins_home as _get_reins_home


def get_reins_home() -> Path:
    return _get_reins_home()