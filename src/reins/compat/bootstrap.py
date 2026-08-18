from __future__ import annotations

import os
import sys
from pathlib import Path


def get_project_root() -> Path:
    runtime_root = os.environ.get("REINS_RUNTIME_ROOT", "").strip()
    if runtime_root:
        return Path(os.path.expandvars(runtime_root)).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def get_vendor_hermes_path() -> Path:
    root = get_project_root()
    candidates = (
        root / "agent",
        root / "hermes-agent",
        root / "vendor" / "hermes-agent",
    )
    return next((path for path in candidates if path.exists()), candidates[-1])


def add_vendor_to_sys_path() -> None:
    vendor_path = get_vendor_hermes_path()

    if not vendor_path.exists():
        raise RuntimeError(
            f"Reins agent runtime directory not found: {vendor_path}\n"
            "The repository checkout is incomplete; clone or update Reins again."
        )

    vendor_path_str = str(vendor_path)

    if vendor_path_str not in sys.path:
        sys.path.insert(0, vendor_path_str)


def apply_bootstrap() -> None:
    add_vendor_to_sys_path()

    try:
        import hermes_bootstrap  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Could not initialize the Reins agent runtime"
        ) from exc
