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
WORD_DESIGN_STYLES = {"professional", "formal", "editorial", "modern", "academic", "minimal", "friendly"}
WORD_TITLE_TREATMENTS = {"plain", "rule", "band", "boxed"}
WORD_HEADING_TREATMENTS = {"plain", "rule", "accent", "shaded"}
WORD_PAGE_SIZES = {"a4", "letter"}
WORD_MARGIN_STYLES = {"compact", "standard", "generous"}
SPREADSHEET_DESIGN_STYLES = {"professional", "financial", "tracker", "dashboard", "minimal", "colorful"}
SPREADSHEET_HEADER_STYLES = {"dark", "accent", "light", "outline"}
SPREADSHEET_ROW_DENSITIES = {"compact", "comfortable", "spacious"}
SPREADSHEET_TABLE_STYLES = {
    "medium1", "medium2", "medium3", "medium4",
    "light1", "light2", "light3", "dark1", "dark2", "none",
}

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


def _normalized_color(value: object) -> str:
    color = str(value or "").strip().lstrip("#").upper()
    return color if _HEX_COLOR.fullmatch(color) else ""


def _normalized_font(value: object) -> str:
    return _PRESENTATION_FONTS.get(str(value or "").strip().casefold(), "")


def normalize_word_design(value: object = None) -> dict[str, Any]:
    design = value if isinstance(value, dict) else {}
    style = str(design.get("style") or "professional").strip().lower()
    title_treatment = str(design.get("title_treatment") or "rule").strip().lower()
    heading_treatment = str(design.get("heading_treatment") or "accent").strip().lower()
    page_size = str(design.get("page_size") or "a4").strip().lower()
    margins = str(design.get("margins") or "standard").strip().lower()
    title_alignment = str(design.get("title_alignment") or "left").strip().lower()
    line_spacing = str(design.get("line_spacing") or "1.15x").strip().lower()
    try:
        body_size = min(max(float(design.get("body_size") or 11), 9), 14)
    except (TypeError, ValueError):
        body_size = 11

    normalized: dict[str, Any] = {
        "style": style if style in WORD_DESIGN_STYLES else "professional",
        "title_treatment": title_treatment if title_treatment in WORD_TITLE_TREATMENTS else "rule",
        "heading_treatment": heading_treatment if heading_treatment in WORD_HEADING_TREATMENTS else "accent",
        "page_size": page_size if page_size in WORD_PAGE_SIZES else "a4",
        "margins": margins if margins in WORD_MARGIN_STYLES else "standard",
        "title_alignment": title_alignment if title_alignment in {"left", "center", "right"} else "left",
        "line_spacing": line_spacing if line_spacing in {"1.0x", "1.15x", "1.3x", "1.5x"} else "1.15x",
        "body_size": body_size,
        "design_reason": str(design.get("design_reason") or "").strip(),
    }
    for key in ("primary", "secondary", "accent", "text", "muted"):
        color = _normalized_color(design.get(key))
        if color:
            normalized[key] = color
    for key in ("heading_font", "body_font"):
        font = _normalized_font(design.get(key))
        if font:
            normalized[key] = font
    return normalized


def normalize_spreadsheet_design(value: object = None) -> dict[str, Any]:
    design = value if isinstance(value, dict) else {}
    style = str(design.get("style") or "professional").strip().lower()
    header_style = str(design.get("header_style") or "dark").strip().lower()
    row_density = str(design.get("row_density") or "comfortable").strip().lower()
    table_style = str(design.get("table_style") or "medium2").strip().lower()
    try:
        zoom = min(max(int(design.get("zoom") or 95), 70), 140)
    except (TypeError, ValueError):
        zoom = 95

    normalized: dict[str, Any] = {
        "style": style if style in SPREADSHEET_DESIGN_STYLES else "professional",
        "header_style": header_style if header_style in SPREADSHEET_HEADER_STYLES else "dark",
        "row_density": row_density if row_density in SPREADSHEET_ROW_DENSITIES else "comfortable",
        "table_style": table_style if table_style in SPREADSHEET_TABLE_STYLES else "medium2",
        "show_title": bool(design.get("show_title", True)),
        "banded_rows": bool(design.get("banded_rows", True)),
        "zoom": zoom,
        "design_reason": str(design.get("design_reason") or "").strip(),
    }
    for key in ("primary", "secondary", "accent", "header_text", "body_text", "band_fill"):
        color = _normalized_color(design.get(key))
        if color:
            normalized[key] = color
    font = _normalized_font(design.get("font"))
    if font:
        normalized["font"] = font
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
            command_count=int(data.get("command_count") or 0),
            metadata=dict(data.get("metadata") or {}),
        )
