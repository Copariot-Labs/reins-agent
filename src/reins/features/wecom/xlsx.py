from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


def _col_name(index: int) -> str:
    name = ""
    value = index

    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name

    return name


def _cell(ref: str, value: object) -> str:
    text = "" if value is None else str(value)
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'


def _row(index: int, values: list[object]) -> str:
    cells = [
        _cell(f"{_col_name(col_index)}{index}", value)
        for col_index, value in enumerate(values, start=1)
    ]
    return f'<row r="{index}">{"".join(cells)}</row>'


def _sheet_name(value: str) -> str:
    cleaned = "".join("_" if char in r'[]:*?/\\' else char for char in value).strip()
    return (cleaned or "Sheet1")[:31]


def write_xlsx(path: Path, *, sheet_name: str, headers: list[str], rows: list[list[object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_sheet = _sheet_name(sheet_name)
    now = datetime.now(timezone.utc).isoformat()
    sheet_rows = [_row(1, headers)]
    for row_index, values in enumerate(rows, start=2):
        sheet_rows.append(_row(row_index, values))

    worksheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    {"".join(sheet_rows)}
  </sheetData>
</worksheet>'''

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
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
    <sheet name="{escape(safe_sheet)}" sheetId="1" r:id="rId1"/>
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
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
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

    return path
