from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from reins.compat.paths import ensure_reins_home
from reins.features.office.schemas import normalize_office_format


def office_home() -> Path:
    path = ensure_reins_home() / "office"
    path.mkdir(parents=True, exist_ok=True)
    return path


def office_documents_dir() -> Path:
    path = office_home() / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def office_index_path() -> Path:
    return office_home() / "documents.jsonl"


def office_previews_dir() -> Path:
    path = office_home() / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def office_backups_dir() -> Path:
    path = office_home() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_slug(value: object, *, default: str = "office-document") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = text.strip("-._")
    return (text[:56] or default).strip("-._") or default


def unique_office_path(*, title: str, office_format: str) -> Path:
    kind = normalize_office_format(office_format)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{safe_slug(title)}-{stamp}"
    candidate = office_documents_dir() / f"{base}.{kind}"

    counter = 2
    while candidate.exists():
        candidate = office_documents_dir() / f"{base}-{counter}.{kind}"
        counter += 1

    return candidate
