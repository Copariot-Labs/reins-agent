from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from reins.compat.paths import ensure_reins_home, ensure_reins_workspace
from reins.features.office.schemas import normalize_office_format


def office_home() -> Path:
    path = ensure_reins_home() / "office"
    path.mkdir(parents=True, exist_ok=True)
    return path


OFFICE_WORKSPACE_FOLDERS = {
    "docx": "Word",
    "xlsx": "Excel",
    "pptx": "PowerPoint",
}


def office_documents_dir(office_format: str | None = None) -> Path:
    if office_format is None:
        return ensure_reins_workspace()
    kind = normalize_office_format(office_format)
    path = ensure_reins_workspace() / OFFICE_WORKSPACE_FOLDERS[kind]
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_office_documents_dir() -> Path:
    return office_home() / "documents"


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
    text = str(value or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-._")
    return (text[:56] or default).strip("-._") or default


def unique_office_path(*, title: str, office_format: str) -> Path:
    kind = normalize_office_format(office_format)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{safe_slug(title)}-{stamp}"
    documents_dir = office_documents_dir(kind)
    candidate = documents_dir / f"{base}.{kind}"

    counter = 2
    while candidate.exists():
        candidate = documents_dir / f"{base}-{counter}.{kind}"
        counter += 1

    return candidate


def _available_destination(source: Path, kind: str) -> Path:
    destination_dir = office_documents_dir(kind)
    candidate = destination_dir / source.name
    counter = 2
    while candidate.exists():
        candidate = destination_dir / f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    return candidate


def migrate_legacy_office_documents() -> int:
    legacy_dir = legacy_office_documents_dir()
    index_path = office_index_path()
    if not legacy_dir.is_dir() or not index_path.exists():
        return 0

    latest_by_id: dict[str, dict[str, object]] = {}
    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0

    for line in lines:
        try:
            payload = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict) and payload.get("id"):
            latest_by_id[str(payload["id"])] = payload

    copied_records: list[tuple[Path, Path, dict[str, object]]] = []
    legacy_root = legacy_dir.resolve()
    for payload in latest_by_id.values():
        source = Path(str(payload.get("path") or "")).expanduser()
        try:
            source = source.resolve()
            source.relative_to(legacy_root)
            kind = normalize_office_format(payload.get("kind"))
        except (OSError, ValueError):
            continue
        if not source.is_file():
            continue

        destination = _available_destination(source, kind)
        try:
            shutil.copy2(source, destination)
        except OSError:
            continue
        updated = dict(payload)
        updated["path"] = str(destination)
        updated["file_name"] = destination.name
        copied_records.append((source, destination, updated))

    if not copied_records:
        return 0

    try:
        with index_path.open("a", encoding="utf-8") as file:
            for _, _, payload in copied_records:
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        for _, destination, _ in copied_records:
            destination.unlink(missing_ok=True)
        return 0

    for source, _, _ in copied_records:
        try:
            source.unlink()
        except OSError:
            pass
    return len(copied_records)
