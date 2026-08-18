from __future__ import annotations

import os
from pathlib import Path

from reins.compat.branding import ensure_reins_branding
from reins.compat.paths import ensure_reins_home, get_reins_home


def prepare_env() -> Path:
    reins_home = ensure_reins_home()

    os.environ["REINS_HOME"] = str(reins_home)

    # Hermes core still reads HERMES_HOME internally.
    # Reins maps Hermes into the Reins data directory.
    os.environ["HERMES_HOME"] = str(reins_home)

    os.environ.setdefault("REINS_PRODUCT_NAME", "Reins")

    # Brand the runtime through its supported SOUL/config interfaces. The
    # vendored agent remains replaceable without carrying a Reins patch set.
    ensure_reins_branding(reins_home)

    return reins_home


def describe_env() -> dict[str, str | None]:
    return {
        "REINS_HOME": os.environ.get("REINS_HOME"),
        "HERMES_HOME": os.environ.get("HERMES_HOME"),
        "resolved_reins_home": str(get_reins_home()),
    }
