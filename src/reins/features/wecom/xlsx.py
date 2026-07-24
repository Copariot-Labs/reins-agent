from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape, quoteattr


# Excel limits cell text to 32,767 characters. XML 1.0 also rejects some
# control characters that can appear in copied chat messages.
MAX_CELL_TEXT_LENGTH = 32_767
_ILLEGAL_XML_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def _safe_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = _ILLEGAL_XML_RE.sub("", text)
    if len(text) > MAX_CELL_TEXT_LENGTH:
        text = text[: MAX_CELL_TEXT_LENGTH - 1] + "…"
    return text


def _col_name(index: int) -> str:
    if index < 1:
        raise ValueError("column index must be greater than zero")

    name = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _cell(ref: str, value: object, *, style: int) -> str:
    text = _safe_text(value)
    # inlineStr keeps untrusted resident content as text, including values that
    # begin with =, +, -, or @. This avoids spreadsheet formula injection.
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{escape(text)}</t></is></c>'
    )


def _row_height(values: Sequence[object], *, header: bool) -> int:
    if header:
        return 30

    longest = 0
    lines = 1
    for value in values:
        text = _safe_text(value)
        longest = max(longest, len(text))
        lines = max(lines, text.count("\n") + 1)

    if lines >= 4 or longest >= 180:
        return 90
    if lines >= 2 or longest >= 80:
        return 64
    return 32


def _row(index: int, values: Sequence[object], *, header: bool = False) -> str:
    style = 1 if header else 2
    cells = [
        _cell(f"{_col_name(col_index)}{index}", value, style=style)
        for col_index, value in enumerate(values, start=1)
    ]
    height = _row_height(values, header=header)
    return f'<row r="{index}" ht="{height}" customHeight="1">{"".join(cells)}</row>'


def _columns(headers: Sequence[str], column_widths: Sequence[float] | None = None) -> str:
    if column_widths is not None and len(column_widths) != len(headers):
        raise ValueError("column_widths must have the same length as headers")

    columns: list[str] = []
    for index, header in enumerate(headers, start=1):
        if column_widths is not None:
            width = float(column_widths[index - 1])
        else:
            width = max(10.0, min(60.0, float(len(_safe_text(header)) + 6)))
        columns.append(
            f'<col min="{index}" max="{index}" width="{width:.1f}" customWidth="1"/>'
        )
    return f'<cols>{"".join(columns)}</cols>'


def _sheet_name(value: str) -> str:
    cleaned = "".join("_" if char in r'[]:*?/\\' else char for char in value).strip()
    return (cleaned or "Sheet1")[:31]


def _write_archive(
    path: Path,
    *,
    sheet_name: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    column_widths: Sequence[float] | None,
) -> None:
    safe_sheet = _sheet_name(sheet_name)
    now = datetime.now(timezone.utc).isoformat()
    sheet_rows = [_row(1, headers, header=True)]
    for row_index, values in enumerate(rows, start=2):
        sheet_rows.append(_row(row_index, values))

    last_column = _col_name(len(headers))
    last_row = max(1, len(rows) + 1)

    worksheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:{last_column}{last_row}"/>
  <sheetViews>
    <sheetView workbookViewId="0" showGridLines="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
      <selection pane="bottomLeft" activeCell="A2" sqref="A2"/>
    </sheetView>
  </sheetViews>
  <sheetFormatPr defaultRowHeight="20"/>
  {_columns(headers, column_widths)}
  <sheetData>
    {"".join(sheet_rows)}
  </sheetData>
  <autoFilter ref="A1:{last_column}{last_row}"/>
</worksheet>'''

    with ZipFile(path, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>''',
        )
        archive.writestr(
            "_rels/.rels",
            '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>''',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name={quoteattr(safe_sheet)} sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>''',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''',
        )
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
        archive.writestr(
            "xl/styles.xml",
            '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/><family val="2"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left/><right/><top/><bottom style="thin"><color rgb="FFD9E2F3"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="3">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <dxfs count="0"/>
  <tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>''',
        )
        archive.writestr(
            "docProps/core.xml",
            f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Reins</dc:creator>
  <cp:lastModifiedBy>Reins</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{escape(now)}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{escape(now)}</dcterms:modified>
</cp:coreProperties>''',
        )
        archive.writestr(
            "docProps/app.xml",
            '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Reins</Application>
</Properties>''',
        )


def write_xlsx(
    path: Path,
    *,
    sheet_name: str,
    headers: list[str],
    rows: list[list[object]],
    column_widths: list[float] | None = None,
) -> Path:
    if not headers:
        raise ValueError("at least one Excel header is required")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file in the same directory and replace atomically.
    # Staff never see a half-written workbook if the process crashes midway.
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        _write_archive(
            temporary_path,
            sheet_name=sheet_name,
            headers=headers,
            rows=rows,
            column_widths=column_widths,
        )
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return path
