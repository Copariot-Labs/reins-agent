from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import uuid4


SUPPORTED_OFFICE_FORMATS = {"docx", "xlsx", "pptx"}

PRESENTATION_STYLES = {"auto", "executive", "modern", "bold", "minimal"}
PRESENTATION_AUDIENCES = {"general", "executive", "client", "team"}
PRESENTATION_DETAIL_LEVELS = {"concise", "balanced", "detailed"}
PRESENTATION_COMPOSITIONS = {"structured", "editorial", "geometric", "split", "spotlight"}
PRESENTATION_MOTIFS = {"lines", "blocks", "circles", "frames"}
PRESENTATION_DESIGN_COLOR_KEYS = (
    "background",
    "surface",
    "primary",
    "secondary",
    "accent",
    "warm",
    "text",
    "muted",
)
PRESENTATION_DESIGN_FONT_KEYS = ("heading_font", "body_font")
PRESENTATION_DESIGN_KEYS = (
    "style",
    "composition",
    "motif",
    *PRESENTATION_DESIGN_COLOR_KEYS,
    *PRESENTATION_DESIGN_FONT_KEYS,
    "palette_reason",
)
PRESENTATION_FONT_CHOICES = (
    "Aptos Display",
    "Aptos",
    "Arial",
    "Calibri",
    "Georgia",
    "Times New Roman",
    "Trebuchet MS",
)

_HEX_COLOR = re.compile(r"^[0-9A-F]{6}$")
_PRESENTATION_FONTS = {font.casefold(): font for font in PRESENTATION_FONT_CHOICES}

OFFICE_MIME_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_FORMAT_ALIASES = {
    "word": "docx",
    "doc": "docx",
    "docx": "docx",
    "document": "docx",
    "excel": "xlsx",
    "xls": "xlsx",
    "xlsx": "xlsx",
    "sheet": "xlsx",
    "spreadsheet": "xlsx",
    "workbook": "xlsx",
    "table": "xlsx",
    "powerpoint": "pptx",
    "ppt": "pptx",
    "pptx": "pptx",
    "presentation": "pptx",
    "slides": "pptx",
    "deck": "pptx",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_office_format(value: object, *, default: str = "docx") -> str:
    text = str(value or default).strip().lower().lstrip(".")
    normalized = _FORMAT_ALIASES.get(text, text)
    if normalized in SUPPORTED_OFFICE_FORMATS:
        return normalized
    return default


def normalize_title(value: object, *, default: str = "Untitled Office Document") -> str:
    title = str(value or "").strip()
    return title or default


def normalize_generator(value: object, *, default: str = "reins") -> str:
    generator = str(value or default).strip().lower()
    return "reins" if generator == "hermes" else (generator or default)


def normalize_presentation_options(value: object = None) -> dict[str, Any]:
    options = value if isinstance(value, dict) else {}

    style = str(options.get("style") or "auto").strip().lower()
    if style not in PRESENTATION_STYLES:
        style = "auto"

    audience = str(options.get("audience") or "general").strip().lower()
    if audience not in PRESENTATION_AUDIENCES:
        audience = "general"

    detail = str(options.get("detail") or "balanced").strip().lower()
    if detail not in PRESENTATION_DETAIL_LEVELS:
        detail = "balanced"

    try:
        slide_count = int(options.get("slide_count") or 8)
    except (TypeError, ValueError):
        slide_count = 8

    return {
        "style": style,
        "audience": audience,
        "detail": detail,
        "slide_count": min(max(slide_count, 5), 15),
    }


def normalize_presentation_design(value: object = None) -> dict[str, str]:
    design = value if isinstance(value, dict) else {}
    style = str(design.get("style") or "modern").strip().lower()
    if style not in PRESENTATION_STYLES or style == "auto":
        style = "modern"

    normalized = {
        "style": style,
        "composition": str(design.get("composition") or "structured").strip().lower(),
        "motif": str(design.get("motif") or "lines").strip().lower(),
        "palette_reason": str(design.get("palette_reason") or "").strip(),
    }
    if normalized["composition"] not in PRESENTATION_COMPOSITIONS:
        normalized["composition"] = "structured"
    if normalized["motif"] not in PRESENTATION_MOTIFS:
        normalized["motif"] = "lines"
    for key in PRESENTATION_DESIGN_COLOR_KEYS:
        color = str(design.get(key) or "").strip().lstrip("#").upper()
        if _HEX_COLOR.fullmatch(color):
            normalized[key] = color
    for key in PRESENTATION_DESIGN_FONT_KEYS:
        font = _PRESENTATION_FONTS.get(str(design.get(key) or "").strip().casefold())
        if font:
            normalized[key] = font
    return normalized


def office_file_name(path: str | Path) -> str:
    return Path(path).name


@dataclass(slots=True)
class OfficeDocumentRecord:
    id: str
    title: str
    kind: str
    path: str
    file_name: str
    mime_type: str
    created_at: str
    updated_at: str = ""
    revision_count: int = 0
    prompt: str = ""
    generator: str = "reins"
    officecli_bin: str | None = None
    command_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        title: str,
        kind: str,
        path: str | Path,
        prompt: str = "",
        generator: str = "reins",
        officecli_bin: str | None = None,
        command_count: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> "OfficeDocumentRecord":
        normalized_kind = normalize_office_format(kind)
        created_at = utc_now_iso()
        return cls(
            id=f"office_{uuid4().hex}",
            title=normalize_title(title),
            kind=normalized_kind,
            path=str(path),
            file_name=office_file_name(path),
            mime_type=OFFICE_MIME_TYPES[normalized_kind],
            created_at=created_at,
            updated_at=created_at,
            revision_count=0,
            prompt=str(prompt or ""),
            generator=normalize_generator(generator),
            officecli_bin=officecli_bin,
            command_count=int(command_count or 0),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OfficeDocumentRecord":
        kind = normalize_office_format(data.get("kind"))
        path = str(data.get("path") or "")
        return cls(
            id=str(data.get("id") or f"office_{uuid4().hex}"),
            title=normalize_title(data.get("title")),
            kind=kind,
            path=path,
            file_name=str(data.get("file_name") or office_file_name(path)),
            mime_type=str(data.get("mime_type") or OFFICE_MIME_TYPES[kind]),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or data.get("created_at") or utc_now_iso()),
            revision_count=int(data.get("revision_count") or 0),
            prompt=str(data.get("prompt") or ""),
            generator=normalize_generator(data.get("generator")),
            officecli_bin=(
                str(data.get("officecli_bin"))
                if data.get("officecli_bin") is not None
                else None
            ),
            command_count=int(data.get("command_count") or 0),
            metadata=dict(data.get("metadata") or {}),
        )
