from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from reins.compat.paths import get_reins_home


def slugify(value: str, *, fallback: str = "artifact") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text or fallback


def artifact_root() -> Path:
    root = get_reins_home() / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_index_path() -> Path:
    return artifact_root() / "artifacts.jsonl"


def dated_artifact_dir() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    path = artifact_root() / today
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_artifact_path(
    *,
    title: str,
    artifact_format: str,
    root: Path | None = None,
) -> Path:
    output_root = root or dated_artifact_dir()
    output_root.mkdir(parents=True, exist_ok=True)

    base = slugify(title)
    suffix = artifact_format.strip().lower().lstrip(".")
    path = output_root / f"{base}.{suffix}"

    counter = 2
    while path.exists():
        path = output_root / f"{base}-{counter}.{suffix}"
        counter += 1

    return path