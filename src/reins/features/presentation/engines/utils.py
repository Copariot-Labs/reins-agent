from __future__ import annotations

import os
from pathlib import Path


def get_venv_python(venv_path: Path) -> Path:
    """
    Return the Python executable inside a virtual environment.

    Supports macOS/Linux and Windows layouts.
    """

    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"

    return venv_path / "bin" / "python"


def directory_has_content(path: Path) -> bool:
    if not path.is_dir():
        return False

    try:
        next(path.iterdir())
    except StopIteration:
        return False

    return True