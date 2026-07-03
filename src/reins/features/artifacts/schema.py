from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


SUPPORTED_ARTIFACT_FORMATS = {
    "docx",
    "xlsx",
    "pptx",
    "txt",
    "json",
}

OFFICE_ARTIFACT_FORMATS = {
    "docx",
    "xlsx",
    "pptx",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_artifact_format(
    value: str | None,
    *,
    default: str = "docx",
) -> str:
    artifact_format = str(value or default).strip().lower().lstrip(".")

    if artifact_format in SUPPORTED_ARTIFACT_FORMATS:
        return artifact_format

    return default


def normalize_title(value: str | None, *, default: str = "Untitled Artifact") -> str:
    title = str(value or "").strip()
    return title or default


@dataclass(slots=True)
class ArtifactRecord:
    id: str
    title: str
    kind: str
    path: str
    created_at: str
    summary: str = ""
    source: str = "reins"
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        title: str,
        kind: str,
        path: str | Path,
        summary: str = "",
        source: str = "reins",
        metadata: dict[str, Any] | None = None,
    ) -> "ArtifactRecord":
        normalized_kind = normalize_artifact_format(kind, default="txt")
        normalized_title = normalize_title(title)

        return cls(
            id=str(uuid4()),
            title=normalized_title,
            kind=normalized_kind,
            path=str(path),
            created_at=utc_now_iso(),
            summary=str(summary or ""),
            source=str(source or "reins"),
            metadata=dict(metadata or {}),
        )

    @property
    def filename(self) -> str:
        return Path(self.path).name

    @property
    def suffix(self) -> str:
        return Path(self.path).suffix.lower().lstrip(".")

    @property
    def exists(self) -> bool:
        return Path(self.path).exists()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRecord":
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or "Untitled Artifact"),
            kind=normalize_artifact_format(str(data.get("kind") or "txt"), default="txt"),
            path=str(data["path"]),
            created_at=str(data.get("created_at") or utc_now_iso()),
            summary=str(data.get("summary") or ""),
            source=str(data.get("source") or "reins"),
            metadata=dict(data.get("metadata") or {}),
        )