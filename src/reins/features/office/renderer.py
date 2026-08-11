from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from reins.features.office.officecli_client import OfficeCliClient
from reins.features.office.schemas import (
    normalize_office_format,
    normalize_presentation_design,
    normalize_spreadsheet_design,
    normalize_title,
    normalize_word_design,
)


class OfficeRenderError(RuntimeError):
    pass


def _text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\x00", "")
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text).strip()


def _body_lines(body: object) -> list[str]:
    if isinstance(body, list):
        raw = "\n".join(str(item) for item in body)
    else:
        raw = str(body or "")
    return [_text(line) for line in raw.splitlines()]


def _safe_sheet_name(value: object, fallback: str) -> str:
    name = _text(value) or fallback
    name = re.sub(r"[\[\]:*?/\\]", "-", name)
    name = name[:31].strip()
    return name or fallback


def _column_name(index: int) -> str:
    if index < 1:
        raise ValueError("Column index must be positive.")
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _prop_args(*props: str) -> list[str]:
    args: list[str] = []
    for prop in props:
        if prop:
            args.extend(["--prop", prop])
    return args


def _run_mutation(client: OfficeCliClient, args: list[object], *, timeout: int = 60) -> None:
    client.run(args, timeout=timeout, allowed_returncodes=(0, 2))


def _office_issue_count(output: str) -> int:
    text = str(output or "").strip()
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return int(data.get("count") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    match = re.search(r"(?:found\s+)?(\d+)\s+issues?", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else 0


@dataclass(frozen=True, slots=True)
class WordTheme:
    primary: str
    secondary: str
    accent: str
    text: str
    muted: str
    heading_font: str
    body_font: str


_WORD_THEMES = {
    "professional": WordTheme("17324D", "E8EEF3", "2B7A78", "24313D", "66727E", "Aptos Display", "Aptos"),
    "formal": WordTheme("1F2937", "ECE8E1", "7C2D12", "222222", "6B7280", "Georgia", "Times New Roman"),
    "editorial": WordTheme("263238", "EEF1F2", "D1495B", "263238", "6A7378", "Georgia", "Aptos"),
    "modern": WordTheme("14213D", "E7F0F4", "007C91", "1F2937", "667085", "Aptos Display", "Aptos"),
    "academic": WordTheme("243B53", "E8EDF2", "486581", "202124", "5F6368", "Georgia", "Times New Roman"),
    "minimal": WordTheme("111827", "F1F3F5", "4B5563", "1F2937", "6B7280", "Arial", "Arial"),
    "friendly": WordTheme("264653", "E9F5F2", "E76F51", "27333A", "66746F", "Trebuchet MS", "Aptos"),
}


def _word_theme(content: dict[str, Any]) -> tuple[dict[str, Any], WordTheme]:
    design = normalize_word_design(content.get("design"))
    base = _WORD_THEMES[design["style"]]
    return design, WordTheme(
        primary=design.get("primary", base.primary),
        secondary=design.get("secondary", base.secondary),
        accent=design.get("accent", base.accent),
        text=design.get("text", base.text),
        muted=design.get("muted", base.muted),
        heading_font=design.get("heading_font", base.heading_font),
        body_font=design.get("body_font", base.body_font),
    )


def _render_docx(content: dict[str, Any], path: Path, client: OfficeCliClient) -> None:
    title = normalize_title(content.get("title"), default="Office Document")
    design, theme = _word_theme(content)
    page_width, page_height = ("21.59cm", "27.94cm") if design["page_size"] == "letter" else ("21cm", "29.7cm")
    margin = {"compact": "1.65cm", "standard": "2.35cm", "generous": "3cm"}[design["margins"]]
    body_size = f"{design['body_size']:g}pt"

    _run_mutation(client, ["set", path, "/", *_prop_args(
        f"title={title}",
        f"pageWidth={page_width}",
        f"pageHeight={page_height}",
        "orientation=portrait",
        f"marginTop={margin}",
        f"marginBottom={margin}",
        f"marginLeft={margin}",
        f"marginRight={margin}",
        f"docDefaults.font={theme.body_font}",
        f"docDefaults.font.hAnsi={theme.body_font}",
        f"docDefaults.fontSize={design['body_size']:g}",
        f"docDefaults.color={theme.text}",
        f"docDefaults.spaceAfter=7pt",
        f"docDefaults.lineSpacing={design['line_spacing']}",
        f"theme.color.dk2={theme.primary}",
        f"theme.color.lt2={theme.secondary}",
        f"theme.color.accent1={theme.accent}",
        f"theme.font.major.latin={theme.heading_font}",
        f"theme.font.minor.latin={theme.body_font}",
    )])

    title_props = [
        f"text={title}", "style=Title", f"font={theme.heading_font}", "size=24pt",
        "bold=true", f"align={design['title_alignment']}", "spaceAfter=18pt", "keepNext=true",
    ]
    if design["title_treatment"] == "band":
        title_props.extend([f"shading.fill={theme.primary}", "color=FFFFFF", "spaceBefore=10pt"])
    elif design["title_treatment"] == "boxed":
        title_props.extend([f"border=single;12;{theme.accent}", f"color={theme.primary}"])
    elif design["title_treatment"] == "rule":
        title_props.extend([f"border.bottom=single;16;{theme.accent}", f"color={theme.primary}"])
    else:
        title_props.append(f"color={theme.primary}")
    _run_mutation(client, ["add", path, "/body", "--type", "paragraph", *_prop_args(*title_props)])

    lines = _body_lines(content.get("body"))
    previous_blank = False
    for raw_line in lines:
        line = _text(raw_line)
        if not line:
            previous_blank = True
            continue
        if line.lower() == title.lower():
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", line)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
        heading = line.endswith(":") and len(line) <= 80 and not bullet and not numbered
        props = [f"text={line}", f"font={theme.body_font}", f"color={theme.text}"]
        if bullet:
            props = [
                f"text={bullet.group(1).strip()}", "listStyle=bullet", f"font={theme.body_font}",
                f"size={body_size}", f"color={theme.text}", "spaceAfter=4pt",
            ]
        elif numbered:
            props = [
                f"text={numbered.group(1).strip()}", "listStyle=ordered", f"font={theme.body_font}",
                f"size={body_size}", f"color={theme.text}", "spaceAfter=4pt",
            ]
        elif heading or (previous_blank and len(line) <= 70):
            props = [
                f"text={line.rstrip(':')}", "style=Heading1", f"font={theme.heading_font}",
                "size=16pt", "bold=true", f"color={theme.primary}", "spaceBefore=14pt",
                "spaceAfter=7pt", "keepNext=true",
            ]
            if design["heading_treatment"] == "rule":
                props.append(f"border.bottom=single;8;{theme.accent}")
            elif design["heading_treatment"] == "accent":
                props.append(f"border.left=single;18;{theme.accent}")
            elif design["heading_treatment"] == "shaded":
                props.append(f"shading.fill={theme.secondary}")
        else:
            props.extend([f"size={body_size}", "spaceAfter=7pt", f"lineSpacing={design['line_spacing']}"])

        _run_mutation(client, ["add", path, "/body", "--type", "paragraph", *_prop_args(*props)])
        previous_blank = False


@dataclass(frozen=True, slots=True)
class SpreadsheetTheme:
    primary: str
    secondary: str
    accent: str
    header_text: str
    body_text: str
    band_fill: str
    font: str


_SPREADSHEET_THEMES = {
    "professional": SpreadsheetTheme("1F4E79", "D9EAF4", "2E75B6", "FFFFFF", "24313D", "F3F7FA", "Aptos"),
    "financial": SpreadsheetTheme("1B4332", "D8F3DC", "B7791F", "FFFFFF", "1F2937", "F0F7F2", "Aptos"),
    "tracker": SpreadsheetTheme("264653", "E9F5F2", "E76F51", "FFFFFF", "27333A", "F3FAF8", "Aptos"),
    "dashboard": SpreadsheetTheme("14213D", "E5ECF2", "007C91", "FFFFFF", "1F2937", "F2F6F8", "Aptos"),
    "minimal": SpreadsheetTheme("374151", "E5E7EB", "6B7280", "FFFFFF", "1F2937", "F9FAFB", "Arial"),
    "colorful": SpreadsheetTheme("3D405B", "F4F1DE", "E07A5F", "FFFFFF", "2D3142", "F7F5EA", "Trebuchet MS"),
}


def _spreadsheet_theme(content: dict[str, Any]) -> tuple[dict[str, Any], SpreadsheetTheme]:
    design = normalize_spreadsheet_design(content.get("design"))
    base = _SPREADSHEET_THEMES[design["style"]]
    return design, SpreadsheetTheme(
        primary=design.get("primary", base.primary),
        secondary=design.get("secondary", base.secondary),
        accent=design.get("accent", base.accent),
        header_text=design.get("header_text", base.header_text),
        body_text=design.get("body_text", base.body_text),
        band_fill=design.get("band_fill", base.band_fill),
        font=design.get("font", base.font),
    )


def _excel_number_format(value: object) -> str:
    formats = {
        "integer": "#,##0",
        "decimal": "#,##0.00",
        "currency": "$#,##0.00",
        "percentage": "0.0%",
        "date": "yyyy-mm-dd",
        "text": "@",
    }
    return formats.get(str(value or "").strip().lower(), "")


def _excel_column_map(items: object, headers: list[Any], value_key: str) -> dict[int, Any]:
    by_name = {str(header).strip().casefold(): index for index, header in enumerate(headers, start=1)}
    result: dict[int, Any] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        column = item.get("column")
        if isinstance(column, int) and 1 <= column <= len(headers):
            index = column
        else:
            index = by_name.get(str(column or "").strip().casefold(), 0)
        if index:
            result[index] = item.get(value_key)
    return result


def _safe_excel_table_name(value: object, index: int) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "", _text(value))
    if not name or name[0].isdigit():
        name = f"ReinsTable{index}"
    return f"{name[:180]}{index}"


def _render_xlsx(content: dict[str, Any], path: Path, client: OfficeCliClient) -> None:
    sheets = content.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        sheets = [{
            "name": "Summary", "subtitle": content.get("body") or "",
            "headers": ["Title", "Details"],
            "rows": [[normalize_title(content.get("title")), content.get("body") or ""]],
        }]
    design, theme = _spreadsheet_theme(content)
    workbook_title = normalize_title(content.get("title"), default="Office Workbook")
    body_height = {"compact": 18, "comfortable": 22, "spacious": 27}[design["row_density"]]

    for sheet_index, raw_sheet in enumerate(sheets, start=1):
        sheet = raw_sheet if isinstance(raw_sheet, dict) else {}
        sheet_name = _safe_sheet_name(sheet.get("name"), f"Sheet{sheet_index}")
        if sheet_index == 1:
            if sheet_name != "Sheet1":
                _run_mutation(client, ["set", path, "/Sheet1", *_prop_args(f"name={sheet_name}")])
        else:
            _run_mutation(client, ["add", path, "/", "--type", "sheet", *_prop_args(f"name={sheet_name}")])

        headers = sheet.get("headers") or sheet.get("columns") or []
        rows = sheet.get("rows") or []
        headers = headers if isinstance(headers, list) else []
        rows = rows if isinstance(rows, list) else []
        if not headers:
            headers = ["Item", "Details"]
        last_column = _column_name(max(1, len(headers)))
        show_title = design["show_title"]
        header_row = 3 if show_title else 1
        first_data_row = header_row + 1
        last_data_row = header_row + len(rows)

        if show_title:
            title = workbook_title if len(sheets) == 1 else f"{workbook_title} - {sheet_name}"
            _run_mutation(client, ["set", path, f"/{sheet_name}/A1", *_prop_args(
                f"value={title}", f"merge=A1:{last_column}1", f"fill={theme.primary}",
                f"font.name={theme.font}", "font.size=16", "font.bold=true",
                f"font.color={theme.header_text}", "alignment.horizontal=left", "alignment.vertical=center",
            )])
            _run_mutation(client, ["set", path, f"/{sheet_name}/row[1]", *_prop_args("height=32")])
            subtitle = _text(sheet.get("subtitle") or content.get("body"))
            if subtitle:
                _run_mutation(client, ["set", path, f"/{sheet_name}/A2", *_prop_args(
                    f"value={_short(subtitle, 180)}", f"merge=A2:{last_column}2", f"fill={theme.secondary}",
                    f"font.name={theme.font}", "font.size=10", f"font.color={theme.body_text}",
                    "alignment.vertical=center", "alignment.wrapText=true",
                )])
            _run_mutation(client, ["set", path, f"/{sheet_name}/row[2]", *_prop_args("height=24")])

        if design["header_style"] == "accent":
            header_fill, header_text = theme.accent, "FFFFFF"
        elif design["header_style"] == "light":
            header_fill, header_text = theme.secondary, theme.primary
        elif design["header_style"] == "outline":
            header_fill, header_text = "FFFFFF", theme.primary
        else:
            header_fill, header_text = theme.primary, theme.header_text

        for column_index, header in enumerate(headers, start=1):
            cell = f"/{sheet_name}/{_column_name(column_index)}{header_row}"
            props = [
                f"value={_text(header)}", "font.bold=true", f"font.name={theme.font}", "font.size=11",
                f"fill={header_fill}", f"font.color={header_text}", "alignment.horizontal=left",
                "alignment.vertical=center", "alignment.wrapText=true",
            ]
            if design["header_style"] == "outline":
                props.extend(["border.bottom=medium", f"border.color={theme.accent}"])
            _run_mutation(client, ["set", path, cell, *_prop_args(*props)])
        _run_mutation(client, ["set", path, f"/{sheet_name}/row[{header_row}]", *_prop_args("height=26")])

        format_map = _excel_column_map(sheet.get("column_formats"), headers, "format")
        width_map = _excel_column_map(sheet.get("column_widths"), headers, "width")
        normalized_rows: list[list[Any]] = []
        for row in rows:
            if isinstance(row, dict):
                normalized_rows.append([row.get(header, "") for header in headers])
            elif isinstance(row, (list, tuple)):
                normalized_rows.append(list(row))
            else:
                normalized_rows.append([row])

        for offset, values in enumerate(normalized_rows):
            row_index = first_data_row + offset
            banded = design["banded_rows"] and offset % 2 == 1
            for column_index in range(1, len(headers) + 1):
                value = values[column_index - 1] if column_index <= len(values) else ""
                props = [
                    f"value={_text(value)}", f"font.name={theme.font}", f"font.color={theme.body_text}",
                    "alignment.vertical=center", "alignment.wrapText=true",
                ]
                if banded:
                    props.append(f"fill={theme.band_fill}")
                number_format = _excel_number_format(format_map.get(column_index))
                if number_format:
                    props.append(f"numberformat={number_format}")
                    if number_format != "@":
                        props.append("alignment.horizontal=right")
                _run_mutation(client, ["set", path, f"/{sheet_name}/{_column_name(column_index)}{row_index}", *_prop_args(*props)])
            _run_mutation(client, ["set", path, f"/{sheet_name}/row[{row_index}]", *_prop_args(f"height={body_height}")])

        for column_index, header in enumerate(headers, start=1):
            requested_width = width_map.get(column_index)
            try:
                width = min(max(float(requested_width), 7), 55) if requested_width is not None else 0
            except (TypeError, ValueError):
                width = 0
            if not width:
                sample = [_text(header), *[_text(row[column_index - 1]) for row in normalized_rows[:40] if column_index <= len(row)]]
                width = min(max(max((len(value) for value in sample), default=10) + 2, 10), 34)
            props = [f"width={width:g}"]
            number_format = _excel_number_format(format_map.get(column_index))
            if number_format:
                props.append(f"numberformat={number_format}")
            _run_mutation(client, ["set", path, f"/{sheet_name}/col[{column_index}]", *_prop_args(*props)])

        if normalized_rows:
            table_ref = f"A{header_row}:{last_column}{last_data_row}"
            _run_mutation(client, ["add", path, f"/{sheet_name}", "--type", "table", *_prop_args(
                f"name={_safe_excel_table_name(sheet_name, sheet_index)}", f"ref={table_ref}",
                f"style={design['table_style']}", "headerRow=true",
                f"showRowStripes={str(design['banded_rows']).lower()}",
            )])

        header_lookup = {str(header).strip().casefold(): index for index, header in enumerate(headers, start=1)}
        if normalized_rows:
            for rule in sheet.get("conditional_highlights") if isinstance(sheet.get("conditional_highlights"), list) else []:
                if not isinstance(rule, dict):
                    continue
                column_index = header_lookup.get(str(rule.get("column") or "").strip().casefold())
                needle = _text(rule.get("contains"))
                fill = str(rule.get("fill") or "").strip().lstrip("#").upper()
                if not column_index or not needle or not re.fullmatch(r"[0-9A-F]{6}", fill):
                    continue
                column = _column_name(column_index)
                _run_mutation(client, ["add", path, f"/{sheet_name}", "--type", "conditionalformatting", *_prop_args(
                    "type=containsText", f"ref={column}{first_data_row}:{column}{last_data_row}",
                    f"text={needle}", f"fill={fill}",
                )])

        _run_mutation(client, ["set", path, f"/{sheet_name}", *_prop_args(
            f"freeze=A{first_data_row}", f"tabColor={theme.accent}", f"zoom={design['zoom']}",
            f"printTitleRows={header_row}:{header_row}",
        )])


@dataclass(frozen=True, slots=True)
class PresentationTheme:
    name: str
    background: str
    surface: str
    primary: str
    secondary: str
    accent: str
    warm: str
    text: str
    muted: str
    heading_font: str
    body_font: str
    composition: str = "structured"
    motif: str = "lines"


_PRESENTATION_THEMES = {
    "executive": PresentationTheme(
        "executive", "F5F7FB", "FFFFFF", "172554", "D6E4F0", "0F766E", "C65D3B",
        "1F2937", "64748B", "Georgia", "Calibri",
    ),
    "modern": PresentationTheme(
        "modern", "F4F7F9", "FFFFFF", "14213D", "DCEAF2", "007C91", "F97316",
        "1F2937", "667085", "Aptos Display", "Aptos",
    ),
    "bold": PresentationTheme(
        "bold", "FFF7ED", "FFFFFF", "202A44", "F9E795", "E84A5F", "0F766E",
        "27272A", "71717A", "Arial", "Arial",
    ),
    "minimal": PresentationTheme(
        "minimal", "F8FAFC", "FFFFFF", "111827", "E2E8F0", "2563EB", "D97706",
        "1F2937", "64748B", "Arial", "Arial",
    ),
}


def _short(value: object, limit: int) -> str:
    value = re.sub(r"\s+", " ", _text(value)).strip()
    if len(value) <= limit:
        return value
    return value[: max(1, limit - 3)].rstrip(" ,.;:-") + "..."


def _mapping_list(value: object, limit: int = 4) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:limit]


def _string_list(value: object, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_short(item, 110) for item in value if _text(item)][:limit]


def _ppt_theme(content: dict[str, Any]) -> PresentationTheme:
    design = normalize_presentation_design(content.get("design"))
    style = design["style"]
    base = _PRESENTATION_THEMES.get(style, _PRESENTATION_THEMES["modern"])
    return PresentationTheme(
        name=style,
        background=design.get("background", base.background),
        surface=design.get("surface", base.surface),
        primary=design.get("primary", base.primary),
        secondary=design.get("secondary", base.secondary),
        accent=design.get("accent", base.accent),
        warm=design.get("warm", base.warm),
        text=design.get("text", base.text),
        muted=design.get("muted", base.muted),
        heading_font=design.get("heading_font", base.heading_font),
        body_font=design.get("body_font", base.body_font),
        composition=design.get("composition", "structured"),
        motif=design.get("motif", "lines"),
    )


def _slide_variant(slide: dict[str, Any], theme: PresentationTheme) -> str:
    variant = _text(slide.get("variant") or "auto").lower()
    if variant in {"editorial", "geometric", "split", "spotlight"}:
        return variant
    return theme.composition


def _add_composition_motif(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
) -> None:
    variant = _slide_variant(slide, theme)
    if theme.motif == "frames":
        _add_ppt_shape(client, path, index, x=0.68, y=0.52, width=32.48, height=0.06, fill=theme.secondary)
        _add_ppt_shape(client, path, index, x=0.68, y=18.46, width=32.48, height=0.06, fill=theme.secondary)
        _add_ppt_shape(client, path, index, x=0.68, y=0.52, width=0.06, height=17.94, fill=theme.secondary)
        _add_ppt_shape(client, path, index, x=33.10, y=0.52, width=0.06, height=17.94, fill=theme.secondary)
    elif theme.motif == "circles":
        for offset, color in ((0.0, theme.accent), (0.62, theme.warm), (1.24, theme.secondary)):
            _add_ppt_shape(
                client, path, index, x=30.55 + offset, y=16.05,
                width=0.42, height=0.42, fill=color, preset="ellipse",
            )
    elif theme.motif == "blocks":
        _add_ppt_shape(client, path, index, x=30.35, y=15.75, width=0.55, height=0.55, fill=theme.accent)
        _add_ppt_shape(client, path, index, x=31.05, y=15.75, width=1.28, height=0.55, fill=theme.warm)
        _add_ppt_shape(client, path, index, x=31.78, y=16.45, width=0.55, height=0.55, fill=theme.primary)
    if variant == "editorial":
        _add_ppt_shape(client, path, index, x=0, y=0, width=0.32, height=19.05, fill=theme.accent)
    elif variant == "geometric":
        _add_ppt_shape(client, path, index, x=30.75, y=0, width=3.12, height=1.10, fill=theme.accent)
        _add_ppt_shape(client, path, index, x=29.82, y=0.22, width=0.58, height=0.58, fill=theme.warm, preset="ellipse")
    elif variant == "split":
        _add_ppt_shape(client, path, index, x=25.95, y=0, width=7.92, height=0.28, fill=theme.accent)
        _add_ppt_shape(client, path, index, x=0, y=18.73, width=10.25, height=0.32, fill=theme.primary)
    elif variant == "spotlight":
        _add_ppt_shape(client, path, index, x=30.70, y=0.72, width=1.65, height=1.65, fill=theme.secondary, preset="ellipse", opacity=0.75)


def _add_ppt_element(
    client: OfficeCliClient,
    path: Path,
    slide_index: int,
    element_type: str,
    **props: object,
) -> None:
    serialized = [f"{name}={value}" for name, value in props.items() if value is not None and value != ""]
    _run_mutation(
        client,
        ["add", path, f"/slide[{slide_index}]", "--type", element_type, *_prop_args(*serialized)],
    )


def _add_ppt_slide(
    client: OfficeCliClient,
    path: Path,
    *,
    background: str,
) -> None:
    _run_mutation(
        client,
        ["add", path, "/", "--type", "slide", *_prop_args("layout=blank", f"background={background}")],
    )


def _add_ppt_text(
    client: OfficeCliClient,
    path: Path,
    slide_index: int,
    *,
    text: object,
    x: float,
    y: float,
    width: float,
    height: float,
    size: int,
    color: str,
    font: str,
    bold: bool = False,
    align: str = "left",
    valign: str = "top",
    opacity: float | None = None,
) -> None:
    clean_text = _text(text)
    if not clean_text:
        return
    _add_ppt_element(
        client,
        path,
        slide_index,
        "shape",
        text=clean_text,
        x=f"{x:.2f}cm",
        y=f"{y:.2f}cm",
        width=f"{width:.2f}cm",
        height=f"{height:.2f}cm",
        font=font,
        size=str(size),
        bold=str(bold).lower(),
        color=color,
        align=align,
        valign=valign,
        opacity=opacity,
        fill="none",
        line="none",
        margin="0.08cm",
        autoFit="normal",
    )


def _add_ppt_shape(
    client: OfficeCliClient,
    path: Path,
    slide_index: int,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    preset: str = "rect",
    line: str = "none",
    opacity: float | None = None,
) -> None:
    _add_ppt_element(
        client,
        path,
        slide_index,
        "shape",
        preset=preset,
        x=f"{x:.2f}cm",
        y=f"{y:.2f}cm",
        width=f"{width:.2f}cm",
        height=f"{height:.2f}cm",
        fill=fill,
        line=line,
        opacity=opacity,
    )


def _add_content_header(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    variant = _slide_variant(slide, theme)
    _add_composition_motif(client, path, index, slide, theme)
    if variant == "editorial":
        eyebrow = _short(slide.get("eyebrow") or f"SECTION {index - 1:02d}", 34).upper()
        _add_ppt_text(
            client, path, index, text=eyebrow, x=1.55, y=0.65, width=9.5, height=0.65,
            size=11, color=theme.accent, font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(slide.get("title"), 92), x=1.50, y=1.45,
            width=24.2, height=2.75, size=34, color=theme.primary, font=theme.heading_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=f"{index:02d}", x=28.05, y=0.62,
            width=3.7, height=2.6, size=42, color=theme.secondary, font=theme.heading_font,
            bold=True, align="right", opacity=0.72,
        )
        return
    if variant == "geometric":
        _add_ppt_shape(client, path, index, x=1.50, y=0.60, width=0.82, height=0.82, fill=theme.accent)
        _add_ppt_shape(client, path, index, x=2.47, y=0.60, width=0.35, height=0.82, fill=theme.warm)
        eyebrow = _short(slide.get("eyebrow") or f"{index - 1:02d}", 34).upper()
        _add_ppt_text(
            client, path, index, text=eyebrow, x=3.25, y=0.62, width=8, height=0.7,
            size=11, color=theme.muted, font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(slide.get("title"), 92), x=1.50, y=1.70,
            width=28.4, height=2.55, size=35, color=theme.primary, font=theme.heading_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=f"{index:02d}/{total:02d}", x=28.8, y=1.70,
            width=2.8, height=0.6, size=10, color=theme.muted, font=theme.body_font, align="right",
        )
        return
    if variant == "split":
        eyebrow = _short(slide.get("eyebrow") or "POINT OF VIEW", 34).upper()
        _add_ppt_text(
            client, path, index, text=eyebrow, x=1.50, y=0.65, width=8, height=0.65,
            size=11, color=theme.accent, font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(slide.get("title"), 92), x=1.50, y=1.45,
            width=22.6, height=2.8, size=34, color=theme.primary, font=theme.heading_font, bold=True,
        )
        _add_ppt_shape(client, path, index, x=26.45, y=1.35, width=4.5, height=1.15, fill=theme.primary)
        _add_ppt_text(
            client, path, index, text=f"{index:02d} / {total:02d}", x=26.75, y=1.56,
            width=3.9, height=0.55, size=10, color="FFFFFF", font=theme.body_font, bold=True, align="center",
        )
        return
    _add_ppt_shape(client, path, index, x=1.50, y=0.75, width=0.34, height=0.34, fill=theme.accent)
    eyebrow = _short(slide.get("eyebrow") or f"{index - 1:02d}", 34).upper()
    _add_ppt_text(
        client, path, index, text=eyebrow, x=2.05, y=0.58, width=7.5, height=0.70,
        size=11, color=theme.muted, font=theme.body_font, bold=True, valign="middle",
    )
    _add_ppt_text(
        client, path, index, text=_short(slide.get("title"), 92), x=1.50, y=1.35,
        width=29.7, height=2.95, size=36, color=theme.primary, font=theme.heading_font, bold=True,
    )
    _add_ppt_text(
        client, path, index, text=f"{index:02d} / {total:02d}", x=30.1, y=0.62,
        width=2.2, height=0.70, size=10, color=theme.muted, font=theme.body_font, align="right",
    )


def _add_takeaway(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
) -> None:
    takeaway = _short(slide.get("takeaway"), 145)
    if not takeaway:
        return
    _add_ppt_shape(
        client, path, index, x=1.50, y=17.15, width=30.87, height=0.11, fill=theme.accent,
    )
    _add_ppt_text(
        client, path, index, text=takeaway, x=1.50, y=17.43, width=30.2, height=0.78,
        size=15, color=theme.text, font=theme.body_font, bold=True, valign="middle",
    )


def _render_cover_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
) -> None:
    variant = _slide_variant(slide, theme)
    eyebrow = _short(slide.get("eyebrow") or "REINS OFFICE", 38).upper()
    title = _short(slide.get("title"), 105)
    subtitle = _short(slide.get("subtitle"), 150)
    takeaway = _short(slide.get("takeaway"), 110)
    if variant == "editorial":
        _add_ppt_slide(client, path, background=theme.background)
        _add_ppt_shape(client, path, index, x=0, y=0, width=1.15, height=19.05, fill=theme.accent)
        _add_ppt_shape(client, path, index, x=1.15, y=0, width=32.72, height=0.72, fill=theme.primary)
        _add_ppt_text(
            client, path, index, text=eyebrow, x=2.15, y=2.15, width=12, height=0.7,
            size=12, color=theme.accent, font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=title, x=2.05, y=3.55, width=27.8, height=6.2,
            size=50 if len(title) < 62 else 42, color=theme.primary, font=theme.heading_font, bold=True,
        )
        _add_ppt_shape(client, path, index, x=2.10, y=10.35, width=7.4, height=0.18, fill=theme.warm)
        _add_ppt_text(
            client, path, index, text=subtitle, x=17.0, y=11.15, width=13.1, height=2.5,
            size=19, color=theme.text, font=theme.body_font,
        )
        _add_ppt_text(
            client, path, index, text=takeaway, x=2.10, y=15.65, width=18, height=1.1,
            size=15, color=theme.muted, font=theme.body_font, bold=True,
        )
        return
    if variant == "split":
        _add_ppt_slide(client, path, background=theme.surface)
        _add_ppt_shape(client, path, index, x=0, y=0, width=12.6, height=19.05, fill=theme.primary)
        _add_ppt_shape(client, path, index, x=11.75, y=0, width=0.85, height=19.05, fill=theme.accent)
        _add_ppt_shape(client, path, index, x=3.0, y=12.0, width=5.5, height=5.5, fill=theme.warm, preset="ellipse", opacity=0.82)
        _add_ppt_text(
            client, path, index, text=eyebrow, x=2.05, y=2.15, width=8.8, height=0.7,
            size=12, color=theme.secondary, font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=title, x=14.65, y=3.25, width=16.4, height=6.1,
            size=43 if len(title) < 62 else 36, color=theme.primary, font=theme.heading_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=subtitle, x=14.7, y=10.1, width=15.2, height=2.6,
            size=19, color=theme.text, font=theme.body_font,
        )
        _add_ppt_text(
            client, path, index, text=takeaway, x=14.7, y=15.5, width=15.2, height=1.2,
            size=15, color=theme.accent, font=theme.body_font, bold=True,
        )
        return
    if variant == "geometric":
        _add_ppt_slide(client, path, background=theme.primary)
        _add_ppt_shape(client, path, index, x=25.1, y=0, width=8.77, height=7.4, fill=theme.accent)
        _add_ppt_shape(client, path, index, x=27.2, y=9.2, width=5.3, height=5.3, fill=theme.warm, preset="ellipse")
        _add_ppt_shape(client, path, index, x=22.7, y=13.9, width=4.2, height=4.2, fill=theme.secondary)
        _add_ppt_text(
            client, path, index, text=eyebrow, x=2.05, y=2.05, width=11, height=0.7,
            size=12, color=theme.secondary, font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=title, x=2.00, y=3.8, width=21.5, height=6.1,
            size=47 if len(title) < 62 else 39, color="FFFFFF", font=theme.heading_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=subtitle, x=2.05, y=10.5, width=18.8, height=2.2,
            size=19, color=theme.secondary, font=theme.body_font,
        )
        _add_ppt_text(
            client, path, index, text=takeaway, x=2.05, y=15.6, width=18.8, height=1.1,
            size=15, color="FFFFFF", font=theme.body_font, bold=True,
        )
        return
    if variant == "spotlight":
        _add_ppt_slide(client, path, background=theme.primary)
        _add_ppt_shape(client, path, index, x=3.2, y=2.0, width=27.4, height=14.5, fill=theme.surface, opacity=0.10)
        _add_ppt_shape(client, path, index, x=15.85, y=2.55, width=2.15, height=2.15, fill=theme.accent, preset="ellipse")
        _add_ppt_text(
            client, path, index, text=eyebrow, x=8.0, y=5.2, width=17.9, height=0.7,
            size=12, color=theme.secondary, font=theme.body_font, bold=True, align="center",
        )
        _add_ppt_text(
            client, path, index, text=title, x=4.5, y=6.4, width=24.9, height=4.5,
            size=45 if len(title) < 62 else 38, color="FFFFFF", font=theme.heading_font,
            bold=True, align="center", valign="middle",
        )
        _add_ppt_text(
            client, path, index, text=subtitle, x=7.0, y=11.4, width=19.9, height=1.9,
            size=18, color=theme.secondary, font=theme.body_font, align="center",
        )
        _add_ppt_text(
            client, path, index, text=takeaway, x=7.0, y=14.6, width=19.9, height=1.0,
            size=14, color=theme.accent, font=theme.body_font, bold=True, align="center",
        )
        return
    _add_ppt_slide(client, path, background=f"{theme.primary}-{theme.accent}-145")
    _add_ppt_shape(client, path, index, x=27.9, y=0, width=5.97, height=19.05, fill=theme.accent, opacity=0.80)
    _add_ppt_shape(client, path, index, x=26.5, y=0, width=0.72, height=19.05, fill=theme.secondary, opacity=0.65)
    _add_ppt_shape(
        client, path, index, x=28.7, y=12.1, width=3.7, height=3.7,
        fill=theme.warm, preset="ellipse", opacity=0.90,
    )
    _add_ppt_text(
        client, path, index, text=eyebrow, x=2.05, y=2.45, width=11, height=0.7,
        size=13, color=theme.secondary, font=theme.body_font, bold=True,
    )
    _add_ppt_text(
        client, path, index, text=title, x=2.00, y=4.15, width=23.3, height=4.85,
        size=44 if len(title) < 62 else 38, color="FFFFFF", font=theme.heading_font, bold=True,
    )
    _add_ppt_text(
        client, path, index, text=subtitle, x=2.05, y=9.15,
        width=21.8, height=2.25, size=20, color=theme.secondary, font=theme.body_font,
    )
    _add_ppt_text(
        client, path, index, text=takeaway, x=2.05, y=15.55,
        width=21.5, height=1.2, size=16, color="FFFFFF", font=theme.body_font, bold=True,
    )


def _card_items(slide: dict[str, Any]) -> list[dict[str, Any]]:
    cards = _mapping_list(slide.get("cards"))
    if cards:
        return cards
    return [
        {"title": f"{index:02d}", "body": bullet}
        for index, bullet in enumerate(_string_list(slide.get("bullets"), 4), start=1)
    ]


def _render_cards_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    items = _card_items(slide) or [{"title": "Key idea", "body": slide.get("body") or slide.get("subtitle")}]
    variant = _slide_variant(slide, theme)
    if variant == "editorial":
        _add_ppt_slide(client, path, background=theme.background)
        _add_content_header(client, path, index, slide, theme, total)
        row_height = min(2.6, 10.7 / max(1, len(items)))
        for item_index, item in enumerate(items, start=1):
            y = 4.65 + (item_index - 1) * row_height
            _add_ppt_text(
                client, path, index, text=f"{item_index:02d}", x=1.55, y=y,
                width=2.1, height=1.1, size=24, color=theme.accent,
                font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(item.get("title"), 58), x=4.15, y=y,
                width=9.0, height=1.1, size=20, color=theme.primary,
                font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(item.get("body"), 175), x=13.7, y=y,
                width=17.9, height=1.4, size=17, color=theme.text, font=theme.body_font,
            )
            _add_ppt_shape(
                client, path, index, x=4.15, y=y + row_height - 0.32,
                width=27.45, height=0.07, fill=theme.secondary,
            )
        _add_takeaway(client, path, index, slide, theme)
        return
    if variant == "split":
        _add_ppt_slide(client, path, background=theme.background)
        _add_content_header(client, path, index, slide, theme, total)
        feature, rest = items[0], items[1:]
        _add_ppt_shape(client, path, index, x=1.50, y=4.55, width=13.2, height=11.1, fill=theme.primary)
        _add_ppt_text(
            client, path, index, text=_short(feature.get("value") or "01", 18), x=2.25, y=5.45,
            width=3.2, height=1.4, size=30, color=theme.secondary, font=theme.heading_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(feature.get("title"), 60), x=2.25, y=7.25,
            width=11.3, height=2.1, size=25, color="FFFFFF", font=theme.heading_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(feature.get("body"), 230), x=2.25, y=10.0,
            width=11.3, height=3.9, size=17, color="FFFFFF", font=theme.body_font,
        )
        rest = rest or [{"title": "Focus", "body": slide.get("takeaway") or slide.get("body")}]
        box_height = min(3.3, 10.45 / max(1, len(rest)))
        for item_index, item in enumerate(rest, start=2):
            y = 4.55 + (item_index - 2) * (box_height + 0.35)
            _add_ppt_shape(client, path, index, x=15.55, y=y, width=16.82, height=box_height, fill=theme.surface)
            _add_ppt_shape(client, path, index, x=15.55, y=y, width=0.28, height=box_height, fill=theme.accent if item_index % 2 == 0 else theme.warm)
            _add_ppt_text(
                client, path, index, text=_short(item.get("title"), 58), x=16.45, y=y + 0.4,
                width=6.0, height=0.95, size=19, color=theme.primary, font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(item.get("body"), 145), x=22.65, y=y + 0.4,
                width=8.9, height=max(1.0, box_height - 0.75), size=16, color=theme.text, font=theme.body_font,
            )
        _add_takeaway(client, path, index, slide, theme)
        return
    if variant in {"geometric", "spotlight"}:
        _add_ppt_slide(client, path, background=theme.background)
        _add_content_header(client, path, index, slide, theme, total)
        count = len(items)
        width = 9.65 if count >= 3 else 14.95
        positions = (
            [(1.50, 5.15), (12.10, 4.50), (22.70, 5.15), (12.10, 10.60)]
            if count >= 3
            else [(1.50, 5.0), (17.42, 5.0)]
        )
        colors = [theme.primary, theme.accent, theme.warm, theme.primary]
        for item_index, (item, (x, y)) in enumerate(zip(items, positions)):
            fill = colors[item_index]
            height = 8.8 if count < 3 else 5.25
            _add_ppt_shape(client, path, index, x=x, y=y, width=width, height=height, fill=fill)
            _add_ppt_shape(client, path, index, x=x + width - 1.2, y=y + 0.35, width=0.72, height=0.72, fill=theme.secondary, preset="ellipse")
            _add_ppt_text(
                client, path, index, text=_short(item.get("value") or f"{item_index + 1:02d}", 18),
                x=x + 0.6, y=y + 0.55, width=2.5, height=1.0, size=19,
                color=theme.secondary, font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(item.get("title"), 52), x=x + 0.6, y=y + 1.75,
                width=width - 1.2, height=1.25, size=20, color="FFFFFF", font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(item.get("body"), 150), x=x + 0.6, y=y + 3.15,
                width=width - 1.2, height=max(1.3, height - 3.65), size=16,
                color="FFFFFF", font=theme.body_font,
            )
        _add_takeaway(client, path, index, slide, theme)
        return
    _add_ppt_slide(client, path, background=theme.background)
    _add_content_header(client, path, index, slide, theme, total)
    if len(items) <= 3:
        count = len(items)
        gap = 0.76
        width = (30.87 - gap * (count - 1)) / count
        boxes = [(1.50 + item_index * (width + gap), 4.55, width, 10.7) for item_index in range(count)]
    else:
        boxes = [(1.50, 4.25, 14.95, 5.55), (17.21, 4.25, 15.16, 5.55),
                 (1.50, 10.55, 14.95, 5.55), (17.21, 10.55, 15.16, 5.55)]
    colors = [theme.accent, theme.warm, theme.primary, theme.accent]
    for item_index, (item, box) in enumerate(zip(items, boxes)):
        x, y, width, height = box
        _add_ppt_shape(client, path, index, x=x, y=y, width=width, height=height, fill=theme.surface)
        _add_ppt_shape(client, path, index, x=x, y=y, width=width, height=0.24, fill=colors[item_index])
        value = _short(item.get("value"), 18)
        if value:
            _add_ppt_text(
                client, path, index, text=value, x=x + 0.55, y=y + 0.65, width=width - 1.1,
                height=1.35, size=30, color=colors[item_index], font=theme.heading_font, bold=True,
            )
            title_y = y + 2.25
        else:
            title_y = y + 0.75
        _add_ppt_text(
            client, path, index, text=_short(item.get("title"), 52), x=x + 0.55, y=title_y,
            width=width - 1.1, height=1.35, size=20, color=theme.primary, font=theme.heading_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(item.get("body"), 165), x=x + 0.55, y=title_y + 1.65,
            width=width - 1.1, height=max(1.4, height - (title_y - y) - 2.3), size=18,
            color=theme.text, font=theme.body_font,
        )
    _add_takeaway(client, path, index, slide, theme)


def _render_kpi_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    stats = _mapping_list(slide.get("stats"))
    if not stats:
        stats = [
            {"value": f"{item_index:02d}", "label": bullet, "detail": ""}
            for item_index, bullet in enumerate(_string_list(slide.get("bullets"), 4), start=1)
        ]
    if not stats:
        _render_cards_slide(client, path, index, slide, theme, total)
        return
    variant = _slide_variant(slide, theme)
    if variant != "structured":
        _add_ppt_slide(client, path, background=theme.background)
        _add_content_header(client, path, index, slide, theme, total)
        hero, rest = stats[0], stats[1:]
        _add_ppt_shape(client, path, index, x=1.50, y=4.55, width=13.55, height=11.15, fill=theme.primary)
        _add_ppt_text(
            client, path, index, text=_short(hero.get("value"), 16), x=2.25, y=5.5,
            width=12.0, height=3.0, size=54, color=theme.secondary, font=theme.heading_font,
            bold=True, align="center", valign="middle",
        )
        _add_ppt_text(
            client, path, index, text=_short(hero.get("label"), 58), x=2.4, y=9.0,
            width=11.7, height=1.6, size=22, color="FFFFFF", font=theme.heading_font,
            bold=True, align="center",
        )
        _add_ppt_text(
            client, path, index, text=_short(hero.get("detail"), 145), x=2.4, y=11.25,
            width=11.7, height=2.4, size=16, color="FFFFFF", font=theme.body_font, align="center",
        )
        rest = rest or [{"value": "--", "label": "Supporting signal", "detail": slide.get("body")}]
        box_height = min(3.35, 10.45 / max(1, len(rest)))
        for stat_index, stat in enumerate(rest, start=1):
            y = 4.55 + (stat_index - 1) * (box_height + 0.35)
            _add_ppt_shape(client, path, index, x=15.85, y=y, width=16.52, height=box_height, fill=theme.surface)
            _add_ppt_text(
                client, path, index, text=_short(stat.get("value"), 16), x=16.55, y=y + 0.45,
                width=4.0, height=1.25, size=28, color=theme.accent, font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(stat.get("label"), 58), x=20.8, y=y + 0.45,
                width=5.1, height=1.1, size=18, color=theme.primary, font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(stat.get("detail"), 100), x=26.0, y=y + 0.45,
                width=5.55, height=max(1.0, box_height - 0.8), size=15, color=theme.text, font=theme.body_font,
            )
        _add_takeaway(client, path, index, slide, theme)
        return
    _add_ppt_slide(client, path, background=theme.background)
    _add_content_header(client, path, index, slide, theme, total)
    count = len(stats)
    gap = 0.76
    width = (30.87 - gap * (count - 1)) / count
    fills = [theme.primary, theme.accent, theme.warm, theme.primary]
    for item_index, stat in enumerate(stats):
        x = 1.50 + item_index * (width + gap)
        fill = fills[item_index]
        _add_ppt_shape(client, path, index, x=x, y=5.0, width=width, height=9.7, fill=fill)
        _add_ppt_text(
            client, path, index, text=_short(stat.get("value"), 16), x=x + 0.45, y=6.0,
            width=width - 0.9, height=2.4, size=44 if width >= 9 else 34,
            color="FFFFFF", font=theme.heading_font, bold=True, align="center", valign="middle",
        )
        _add_ppt_text(
            client, path, index, text=_short(stat.get("label"), 58), x=x + 0.5, y=8.7,
            width=width - 1.0, height=1.6, size=19, color="FFFFFF", font=theme.body_font,
            bold=True, align="center",
        )
        _add_ppt_text(
            client, path, index, text=_short(stat.get("detail"), 115), x=x + 0.5, y=11.0,
            width=width - 1.0, height=2.5, size=16, color="FFFFFF", font=theme.body_font,
            align="center",
        )
    _add_takeaway(client, path, index, slide, theme)


def _render_comparison_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    _add_ppt_slide(client, path, background=theme.background)
    columns = _mapping_list(slide.get("columns"), 2)
    if len(columns) < 2:
        bullets = _string_list(slide.get("bullets"), 6)
        midpoint = max(1, (len(bullets) + 1) // 2)
        columns = [
            {"title": "Current view", "bullets": bullets[:midpoint]},
            {"title": "Forward view", "bullets": bullets[midpoint:]},
        ]
    variant = _slide_variant(slide, theme)
    if variant in {"editorial", "geometric", "spotlight"}:
        _add_content_header(client, path, index, slide, theme, total)
        fills = [theme.primary, theme.surface]
        text_colors = ["FFFFFF", theme.text]
        for column_index, column in enumerate(columns[:2]):
            y = 4.55 + column_index * 5.75
            _add_ppt_shape(client, path, index, x=1.50, y=y, width=30.87, height=5.05, fill=fills[column_index])
            _add_ppt_text(
                client, path, index, text=f"0{column_index + 1}", x=2.15, y=y + 0.65,
                width=2.0, height=1.2, size=24, color=theme.accent if column_index else theme.secondary,
                font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(column.get("title"), 52), x=4.55, y=y + 0.65,
                width=8.2, height=1.3, size=22, color=theme.secondary if column_index == 0 else theme.primary,
                font=theme.heading_font, bold=True,
            )
            body_parts = []
            if _text(column.get("body")):
                body_parts.append(_short(column.get("body"), 130))
            body_parts.extend(_string_list(column.get("bullets"), 4))
            _add_ppt_text(
                client, path, index, text="  /  ".join(body_parts), x=13.25, y=y + 0.62,
                width=18.0, height=3.25, size=16, color=text_colors[column_index], font=theme.body_font,
                valign="middle",
            )
        _add_takeaway(client, path, index, slide, theme)
        return
    _add_content_header(client, path, index, slide, theme, total)
    fills = [theme.primary, theme.surface]
    text_colors = ["FFFFFF", theme.text]
    heading_colors = [theme.secondary, theme.accent]
    for column_index, column in enumerate(columns[:2]):
        x = 1.50 + column_index * 15.82
        _add_ppt_shape(client, path, index, x=x, y=4.45, width=15.05, height=11.35, fill=fills[column_index])
        _add_ppt_text(
            client, path, index, text=_short(column.get("title"), 52), x=x + 0.75, y=5.25,
            width=13.55, height=1.4, size=23, color=heading_colors[column_index],
            font=theme.heading_font, bold=True,
        )
        body_parts = []
        if _text(column.get("body")):
            body_parts.append(_short(column.get("body"), 150))
        body_parts.extend(f"{item_index:02d}  {bullet}" for item_index, bullet in enumerate(
            _string_list(column.get("bullets"), 4), start=1,
        ))
        _add_ppt_text(
            client, path, index, text="\n\n".join(body_parts), x=x + 0.75, y=7.1,
            width=13.55, height=7.4, size=18, color=text_colors[column_index], font=theme.body_font,
        )
    _add_takeaway(client, path, index, slide, theme)


def _render_timeline_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    steps = _mapping_list(slide.get("steps"))
    if not steps:
        steps = [{"title": item, "body": ""} for item in _string_list(slide.get("bullets"), 4)]
    if not steps:
        _render_cards_slide(client, path, index, slide, theme, total)
        return
    _add_ppt_slide(client, path, background=theme.background)
    _add_content_header(client, path, index, slide, theme, total)
    variant = _slide_variant(slide, theme)
    if variant != "structured":
        count = len(steps)
        row_height = min(2.65, 10.7 / max(1, count))
        _add_ppt_shape(
            client, path, index, x=3.0, y=5.05, width=0.12,
            height=max(0.2, row_height * (count - 1)), fill=theme.secondary,
        )
        colors = [theme.accent, theme.primary, theme.warm, theme.accent]
        for step_index, step in enumerate(steps, start=1):
            y = 4.62 + (step_index - 1) * row_height
            color = colors[(step_index - 1) % len(colors)]
            _add_ppt_shape(client, path, index, x=2.35, y=y, width=1.42, height=1.42, fill=color, preset="ellipse")
            _add_ppt_text(
                client, path, index, text=f"{step_index:02d}", x=2.4, y=y + 0.13,
                width=1.3, height=0.95, size=14, color="FFFFFF", font=theme.body_font,
                bold=True, align="center", valign="middle",
            )
            _add_ppt_text(
                client, path, index, text=_short(step.get("title"), 48), x=4.55, y=y + 0.05,
                width=8.8, height=1.15, size=20, color=theme.primary, font=theme.heading_font, bold=True,
            )
            _add_ppt_text(
                client, path, index, text=_short(step.get("body"), 145), x=14.0, y=y + 0.05,
                width=17.5, height=1.35, size=16, color=theme.text, font=theme.body_font,
            )
        _add_takeaway(client, path, index, slide, theme)
        return
    count = len(steps)
    width = 6.25 if count == 4 else min(8.8, 27.5 / count)
    first_center = 1.50 + width / 2
    last_center = 32.37 - width / 2
    centers = [
        first_center + item_index * ((last_center - first_center) / max(1, count - 1))
        for item_index in range(count)
    ]
    if count == 1:
        centers = [16.93]
    _add_ppt_shape(client, path, index, x=centers[0], y=7.42, width=max(0.2, centers[-1] - centers[0]), height=0.12, fill=theme.secondary)
    colors = [theme.accent, theme.primary, theme.warm, theme.accent]
    for step_index, (step, center) in enumerate(zip(steps, centers), start=1):
        color = colors[(step_index - 1) % len(colors)]
        _add_ppt_shape(client, path, index, x=center - 0.68, y=6.80, width=1.36, height=1.36, fill=color, preset="ellipse")
        _add_ppt_text(
            client, path, index, text=f"{step_index:02d}", x=center - 0.65, y=6.86,
            width=1.3, height=1.1, size=16, color="FFFFFF", font=theme.body_font,
            bold=True, align="center", valign="middle",
        )
        _add_ppt_text(
            client, path, index, text=_short(step.get("title"), 42), x=center - width / 2, y=8.85,
            width=width, height=1.25, size=20, color=theme.primary, font=theme.heading_font,
            bold=True, align="center",
        )
        _add_ppt_text(
            client, path, index, text=_short(step.get("body"), 105), x=center - width / 2, y=10.45,
            width=width, height=3.1, size=17, color=theme.text, font=theme.body_font, align="center",
        )
    _add_takeaway(client, path, index, slide, theme)


def _chart_number(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", _text(value).replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _chart_spec(slide: dict[str, Any]) -> tuple[str, list[str], list[dict[str, Any]]] | None:
    chart = slide.get("chart") if isinstance(slide.get("chart"), dict) else {}
    chart_type = _text(chart.get("type") or "column").lower()
    if chart_type not in {"column", "bar", "line", "area", "pie", "doughnut"}:
        chart_type = "column"
    categories = [_short(item, 28).replace(",", " / ") for item in _string_list(chart.get("categories"), 10)]
    series: list[dict[str, Any]] = []
    for raw_series in _mapping_list(chart.get("series"), 4):
        values = raw_series.get("values") if isinstance(raw_series.get("values"), list) else []
        numbers = [_chart_number(item) for item in values]
        if not numbers or any(item is None for item in numbers):
            continue
        if categories and len(numbers) != len(categories):
            continue
        series.append({"name": _short(raw_series.get("name") or "Series", 28), "values": numbers})
    if not categories or not series:
        return None
    return chart_type, categories, series


def _render_chart_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    spec = _chart_spec(slide)
    if not spec:
        _render_cards_slide(client, path, index, slide, theme, total)
        return
    _add_ppt_slide(client, path, background=theme.background)
    _add_content_header(client, path, index, slide, theme, total)
    chart_type, categories, series = spec
    chart = slide.get("chart") if isinstance(slide.get("chart"), dict) else {}
    alternate = _slide_variant(slide, theme) != "structured"
    chart_x = 11.92 if alternate else 1.50
    insight_x = 1.50 if alternate else 22.75
    props: dict[str, object] = {
        "chartType": chart_type,
        "categories": ",".join(categories),
        "x": f"{chart_x:.2f}cm",
        "y": "4.35cm",
        "width": "20.45cm",
        "height": "11.65cm",
        "title": _short(chart.get("title"), 70),
        "legend": "bottom",
    }
    colors = [theme.primary, theme.accent, theme.warm, theme.secondary]
    for series_index, item in enumerate(series, start=1):
        props[f"series{series_index}.name"] = item["name"]
        props[f"series{series_index}.values"] = ",".join(f"{value:g}" for value in item["values"])
        props[f"series{series_index}.color"] = colors[series_index - 1]
    _add_ppt_element(client, path, index, "chart", **props)
    _add_ppt_shape(client, path, index, x=insight_x, y=4.35, width=9.62, height=11.65, fill=theme.primary)
    _add_ppt_text(
        client, path, index, text="KEY INSIGHT", x=insight_x + 0.70, y=5.15, width=8.2, height=0.7,
        size=12, color=theme.secondary, font=theme.body_font, bold=True,
    )
    insight = slide.get("takeaway") or slide.get("body") or "\n".join(_string_list(slide.get("bullets"), 3))
    _add_ppt_text(
        client, path, index, text=_short(insight, 230), x=insight_x + 0.70, y=6.35, width=8.2,
        height=7.8, size=20, color="FFFFFF", font=theme.heading_font, bold=True,
    )
    _add_takeaway(client, path, index, slide, theme)


def _render_statement_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    _add_ppt_slide(client, path, background=theme.background)
    _add_content_header(client, path, index, slide, theme, total)
    statement = slide.get("body") or slide.get("subtitle") or slide.get("takeaway")
    bullets = _string_list(slide.get("bullets"), 4)
    if _slide_variant(slide, theme) != "structured":
        _add_ppt_shape(client, path, index, x=1.50, y=4.55, width=30.87, height=7.0, fill=theme.surface)
        _add_ppt_shape(client, path, index, x=1.50, y=4.55, width=0.35, height=7.0, fill=theme.accent)
        _add_ppt_text(
            client, path, index, text=_short(statement, 270), x=2.65, y=5.25,
            width=28.2, height=5.4, size=31, color=theme.primary,
            font=theme.heading_font, bold=True, valign="middle", align="center",
        )
        if bullets:
            gap = 0.55
            width = (30.87 - gap * (len(bullets) - 1)) / len(bullets)
            for bullet_index, bullet in enumerate(bullets, start=1):
                x = 1.50 + (bullet_index - 1) * (width + gap)
                _add_ppt_shape(client, path, index, x=x, y=12.35, width=width, height=3.25, fill=theme.primary if bullet_index == 1 else theme.secondary)
                _add_ppt_text(
                    client, path, index, text=f"{bullet_index:02d}", x=x + 0.4, y=12.75,
                    width=1.25, height=0.7, size=13, color=theme.accent,
                    font=theme.body_font, bold=True,
                )
                _add_ppt_text(
                    client, path, index, text=bullet, x=x + 0.4, y=13.55,
                    width=width - 0.8, height=1.45, size=15,
                    color="FFFFFF" if bullet_index == 1 else theme.primary,
                    font=theme.body_font, bold=True,
                )
        _add_takeaway(client, path, index, slide, theme)
        return
    _add_ppt_shape(client, path, index, x=1.50, y=4.55, width=20.3, height=10.55, fill=theme.primary)
    _add_ppt_text(
        client, path, index, text=_short(statement, 250), x=2.35, y=5.55, width=18.6,
        height=7.8, size=28, color="FFFFFF", font=theme.heading_font, bold=True, valign="middle",
    )
    for bullet_index, bullet in enumerate(bullets, start=1):
        y = 4.75 + (bullet_index - 1) * 2.75
        _add_ppt_shape(client, path, index, x=23.15, y=y, width=1.15, height=1.15, fill=theme.accent, preset="ellipse")
        _add_ppt_text(
            client, path, index, text=f"{bullet_index:02d}", x=23.15, y=y + 0.04, width=1.15,
            height=0.95, size=13, color="FFFFFF", font=theme.body_font, bold=True,
            align="center", valign="middle",
        )
        _add_ppt_text(
            client, path, index, text=bullet, x=24.75, y=y - 0.05, width=7.4,
            height=1.7, size=17, color=theme.text, font=theme.body_font, valign="middle",
        )
    _add_takeaway(client, path, index, slide, theme)


def _render_quote_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    quote = slide.get("quote") or slide.get("body") or slide.get("takeaway") or slide.get("title")
    if _slide_variant(slide, theme) != "structured":
        _add_ppt_slide(client, path, background=theme.background)
        _add_composition_motif(client, path, index, slide, theme)
        _add_ppt_shape(client, path, index, x=2.0, y=2.15, width=6.1, height=6.1, fill=theme.accent, preset="ellipse")
        _add_ppt_text(
            client, path, index, text='"', x=2.75, y=1.95, width=4.6, height=4.4,
            size=58, color="FFFFFF", font=theme.heading_font, bold=True, align="center", valign="middle",
        )
        _add_ppt_text(
            client, path, index, text=_short(slide.get("eyebrow") or "PERSPECTIVE", 32).upper(),
            x=10.0, y=2.25, width=12, height=0.7, size=12, color=theme.accent,
            font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(quote, 310), x=9.9, y=4.0, width=21.7,
            height=8.2, size=31, color=theme.primary, font=theme.heading_font, bold=True, valign="middle",
        )
        _add_ppt_shape(client, path, index, x=10.0, y=13.1, width=6.5, height=0.14, fill=theme.warm)
        _add_ppt_text(
            client, path, index, text=_short(slide.get("attribution"), 90), x=10.0, y=13.65,
            width=18, height=1.1, size=17, color=theme.muted, font=theme.body_font,
        )
        _add_ppt_text(
            client, path, index, text=f"{index:02d} / {total:02d}", x=29.8, y=17.45,
            width=2.4, height=0.6, size=10, color=theme.muted, font=theme.body_font, align="right",
        )
        return
    _add_ppt_slide(client, path, background=theme.primary)
    _add_ppt_shape(client, path, index, x=2.0, y=3.0, width=1.25, height=8.5, fill=theme.warm)
    _add_ppt_text(
        client, path, index, text=_short(slide.get("eyebrow") or "PERSPECTIVE", 32).upper(),
        x=4.35, y=2.3, width=10, height=0.7, size=12, color=theme.secondary,
        font=theme.body_font, bold=True,
    )
    _add_ppt_text(
        client, path, index, text=_short(quote, 310), x=4.25, y=4.0, width=25.5,
        height=7.3, size=30, color="FFFFFF", font=theme.heading_font, bold=True, valign="middle",
    )
    _add_ppt_text(
        client, path, index, text=_short(slide.get("attribution"), 90), x=4.35, y=13.1,
        width=20, height=1.1, size=17, color=theme.secondary, font=theme.body_font,
    )
    _add_ppt_text(
        client, path, index, text=f"{index:02d} / {total:02d}", x=29.8, y=17.45,
        width=2.4, height=0.6, size=10, color=theme.secondary, font=theme.body_font, align="right",
    )


def _render_closing_slide(
    client: OfficeCliClient,
    path: Path,
    index: int,
    slide: dict[str, Any],
    theme: PresentationTheme,
    total: int,
) -> None:
    bullets = _string_list(slide.get("bullets"), 3)
    if _slide_variant(slide, theme) != "structured":
        _add_ppt_slide(client, path, background=theme.background)
        _add_composition_motif(client, path, index, slide, theme)
        _add_ppt_shape(client, path, index, x=0, y=0, width=10.8, height=19.05, fill=theme.primary)
        _add_ppt_text(
            client, path, index, text=_short(slide.get("eyebrow") or "NEXT MOVE", 32).upper(),
            x=1.65, y=2.15, width=7.5, height=0.65, size=12, color=theme.secondary,
            font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=_short(slide.get("takeaway"), 150), x=1.65, y=4.0,
            width=7.6, height=8.2, size=25, color="FFFFFF", font=theme.heading_font, bold=True,
            valign="middle",
        )
        _add_ppt_text(
            client, path, index, text=_short(slide.get("title"), 100), x=13.0, y=2.55,
            width=17.8, height=3.6, size=40, color=theme.primary, font=theme.heading_font, bold=True,
        )
        for bullet_index, bullet in enumerate(bullets, start=1):
            y = 7.35 + (bullet_index - 1) * 2.8
            _add_ppt_shape(client, path, index, x=13.05, y=y, width=1.2, height=1.2, fill=theme.accent, preset="ellipse")
            _add_ppt_text(
                client, path, index, text=f"{bullet_index:02d}", x=13.08, y=y + 0.09,
                width=1.14, height=0.9, size=13, color="FFFFFF", font=theme.body_font,
                bold=True, align="center", valign="middle",
            )
            _add_ppt_text(
                client, path, index, text=bullet, x=15.0, y=y - 0.05,
                width=15.8, height=1.5, size=18, color=theme.text, font=theme.body_font,
                bold=True, valign="middle",
            )
        _add_ppt_text(
            client, path, index, text=f"{index:02d} / {total:02d}", x=29.8, y=17.45,
            width=2.4, height=0.6, size=10, color=theme.muted, font=theme.body_font, align="right",
        )
        return
    _add_ppt_slide(client, path, background=f"{theme.primary}-{theme.accent}-150")
    _add_ppt_shape(client, path, index, x=0, y=0, width=1.0, height=19.05, fill=theme.warm)
    _add_ppt_text(
        client, path, index, text=_short(slide.get("eyebrow") or "NEXT MOVE", 32).upper(),
        x=2.4, y=2.25, width=10, height=0.65, size=12, color=theme.secondary,
        font=theme.body_font, bold=True,
    )
    _add_ppt_text(
        client, path, index, text=_short(slide.get("title"), 100), x=2.35, y=3.8,
        width=26.7, height=3.7, size=42, color="FFFFFF", font=theme.heading_font, bold=True,
    )
    for bullet_index, bullet in enumerate(bullets, start=1):
        x = 2.35 + (bullet_index - 1) * 9.75
        _add_ppt_shape(client, path, index, x=x, y=9.3, width=8.9, height=3.65, fill=theme.surface)
        _add_ppt_text(
            client, path, index, text=f"{bullet_index:02d}", x=x + 0.55, y=9.85,
            width=1.4, height=0.8, size=14, color=theme.accent, font=theme.body_font, bold=True,
        )
        _add_ppt_text(
            client, path, index, text=bullet, x=x + 0.55, y=10.75, width=7.75,
            height=1.65, size=17, color=theme.primary, font=theme.body_font, bold=True,
        )
    _add_ppt_text(
        client, path, index, text=_short(slide.get("takeaway"), 150), x=2.4, y=15.25,
        width=26, height=1.4, size=18, color=theme.secondary, font=theme.body_font, bold=True,
    )
    _add_ppt_text(
        client, path, index, text=f"{index:02d} / {total:02d}", x=29.8, y=17.45,
        width=2.4, height=0.6, size=10, color=theme.secondary, font=theme.body_font, align="right",
    )


def _speaker_notes(slide: dict[str, Any]) -> str:
    explicit = _short(slide.get("notes"), 900)
    if explicit:
        return explicit
    parts = [slide.get("takeaway"), slide.get("body"), *(_string_list(slide.get("bullets"), 4))]
    body = " ".join(_short(part, 180) for part in parts if _text(part))
    return body or f"Introduce and explain {_short(slide.get('title'), 120)}."


def _render_pptx(content: dict[str, Any], path: Path, client: OfficeCliClient) -> None:
    deck_title = normalize_title(content.get("title"), default="Office Presentation")
    slides = content.get("slides")
    if not isinstance(slides, list) or not slides:
        slides = [
            {"layout": "cover", "title": deck_title, "subtitle": "Prepared by Reins Office"},
            {"layout": "cards", "title": "The essential points", "bullets": _body_lines(content.get("body"))[:4]},
            {"layout": "closing", "title": "Turn the discussion into action"},
        ]

    theme = _ppt_theme(content)
    total = len(slides)
    for index, raw_slide in enumerate(slides, start=1):
        slide = raw_slide if isinstance(raw_slide, dict) else {}
        slide = {**slide, "title": _text(slide.get("title")) or deck_title}
        layout = _text(slide.get("layout")).lower()
        if index == 1:
            layout = "cover"

        if layout == "cover":
            _render_cover_slide(client, path, index, slide, theme)
        elif layout == "kpi":
            _render_kpi_slide(client, path, index, slide, theme, total)
        elif layout == "comparison":
            _render_comparison_slide(client, path, index, slide, theme, total)
        elif layout == "timeline":
            _render_timeline_slide(client, path, index, slide, theme, total)
        elif layout == "chart":
            _render_chart_slide(client, path, index, slide, theme, total)
        elif layout == "quote":
            _render_quote_slide(client, path, index, slide, theme, total)
        elif layout == "closing":
            _render_closing_slide(client, path, index, slide, theme, total)
        elif layout in {"agenda", "cards"}:
            _render_cards_slide(client, path, index, slide, theme, total)
        else:
            _render_statement_slide(client, path, index, slide, theme, total)

        _add_ppt_element(client, path, index, "notes", text=_speaker_notes(slide))


def render_office_content(
    *,
    office_format: str,
    content: dict[str, Any],
    output_path: str | Path,
    client: OfficeCliClient | None = None,
) -> Path:
    normalized = normalize_office_format(office_format)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    client = client or OfficeCliClient()

    _run_mutation(client, ["create", path], timeout=60)
    _run_mutation(client, ["open", path], timeout=60)

    try:
        if normalized == "xlsx":
            _render_xlsx(content, path, client)
        elif normalized == "pptx":
            _render_pptx(content, path, client)
        else:
            _render_docx(content, path, client)
    finally:
        try:
            _run_mutation(client, ["close", path], timeout=60)
        except Exception:
            pass

    client.run(["validate", path], timeout=60, allowed_returncodes=(0, 2))
    if normalized == "pptx":
        issues = client.run(
            ["view", path, "issues", "--json"],
            timeout=90,
            allowed_returncodes=(0, 2),
            env_overrides={"OFFICECLI_NO_AUTO_RESIDENT": "1"},
        )
        issue_count = _office_issue_count(issues.stdout or issues.stderr)
        if issue_count:
            raise OfficeRenderError(
                f"OfficeCLI found {issue_count} presentation layout issue(s). "
                "Shorten the requested slide copy or revise the presentation structure."
            )
    return path
