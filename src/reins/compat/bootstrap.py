from __future__ import annotations

import sys
from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_vendor_hermes_path() -> Path:
    return get_project_root() / "vendor" / "hermes-agent"


def add_vendor_to_sys_path() -> None:
    vendor_path = get_vendor_hermes_path()

    if not vendor_path.exists():
        raise RuntimeError(
            f"Hermes vendor directory not found: {vendor_path}\n"
            "Run: git submodule update --init --recursive"
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
            "Could not import hermes_bootstrap from vendor/hermes-agent"
        ) from exc