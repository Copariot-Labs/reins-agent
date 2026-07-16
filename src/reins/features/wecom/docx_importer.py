from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from reins.features.wecom.engine import load_faq_entries, save_faq_entries


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
HEADER_ALIASES = {
    "sequence": ("序号", "编号"),
    "question_type": ("问题类型", "类型", "分类"),
    "question": ("常见问题表述", "问题", "问法"),
    "answer": ("回答", "推荐答复要点", "答复", "答案"),
}


@dataclass(frozen=True)
class DocxFaqRow:
    sequence: str
    question_type: str
    question: str
    answer: str
    source_row: int


def _node_text(node: ET.Element) -> str:
    return "".join(t.text or "" for t in node.findall(".//w:t", NS)).strip()


def _cell_text(cell: ET.Element) -> str:
    paragraphs = [_node_text(p) for p in cell.findall(".//w:p", NS)]
    return "\n".join(text for text in paragraphs if text).strip()


def _table_rows(table: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.findall("./w:tr", NS):
        cells = [_cell_text(tc) for tc in tr.findall("./w:tc", NS)]
        if any(cells):
            rows.append(cells)
    return rows


def _all_table_rows(path: Path) -> list[list[str]]:
    with ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    rows: list[list[str]] = []
    for table in root.findall(".//w:tbl", NS):
        rows.extend(_table_rows(table))
    return rows


def _normalized_header(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _header_indices(row: list[str]) -> dict[str, int] | None:
    normalized = [_normalized_header(value) for value in row]
    indices: dict[str, int] = {}

    for key, aliases in HEADER_ALIASES.items():
        exact_index = next(
            (index for index, value in enumerate(normalized) if value in aliases),
            None,
        )
        if exact_index is not None:
            indices[key] = exact_index
            continue

        for index, value in enumerate(normalized):
            if any(len(alias) >= 3 and alias in value for alias in aliases):
                indices[key] = index
                break

    if "question" not in indices or "answer" not in indices:
        return None

    return indices


def _row_value(row: list[str], index: int | None) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _sequence_number(value: str) -> int | None:
    match = re.search(r"\d+", value or "")
    if not match:
        return None
    return int(match.group(0))


def _looks_like_continuation(value: str) -> bool:
    return value.strip().startswith("（第") or value.strip().startswith("(第")


def _extract_rows(path: Path) -> list[DocxFaqRow]:
    raw_rows = _all_table_rows(path)
    extracted: list[DocxFaqRow] = []
    header: dict[str, int] | None = None

    for source_row, row in enumerate(raw_rows, start=1):
        maybe_header = _header_indices(row)
        if maybe_header:
            header = maybe_header
            continue

        if header is None:
            continue

        sequence = _row_value(row, header.get("sequence"))
        question = _row_value(row, header.get("question"))
        answer = _row_value(row, header.get("answer"))
        question_type = _row_value(row, header.get("question_type"))

        if not question or not answer:
            continue
        if _looks_like_continuation(question) or _looks_like_continuation(sequence):
            continue
        if "常见问题表述" in question or question == "问题":
            continue

        extracted.append(
            DocxFaqRow(
                sequence=sequence,
                question_type=question_type,
                question=question,
                answer=answer,
                source_row=source_row,
            )
        )

    return extracted


def _skip_template_examples(rows: list[DocxFaqRow]) -> list[DocxFaqRow]:
    reset_index: int | None = None
    previous: int | None = None

    for index, row in enumerate(rows):
        current = _sequence_number(row.sequence)
        if current == 1 and previous is not None and previous > 1:
            reset_index = index
        if current is not None:
            previous = current

    if reset_index is None:
        return rows

    return rows[reset_index:]


def infer_community_name(path: Path) -> str:
    name = path.stem
    match = re.search(r"[（(]([^）)]+)[）)]", name)
    if match:
        return match.group(1).strip()
    return name.replace("社区日常问题解答", "").strip(" -_") or "default"


def _entry_id(*, community: str, question_type: str, question: str) -> str:
    digest = hashlib.sha1(f"{community}|{question_type}|{question}".encode("utf-8")).hexdigest()[:12]
    return f"docx_{digest}"


def _entry_from_row(row: DocxFaqRow, *, community: str, source_file: Path) -> dict:
    return {
        "id": _entry_id(
            community=community,
            question_type=row.question_type,
            question=row.question,
        ),
        "enabled": True,
        "meaning": " / ".join(part for part in [community, row.question_type, row.question] if part),
        "approved_answer": row.answer,
        "questions": [row.question],
        "keywords": [],
        "patterns": [],
        "community": community,
        "question_type": row.question_type,
        "source": {
            "kind": "docx",
            "file": str(source_file),
            "row": row.source_row,
        },
    }


def import_docx_faq(
    path: str | Path,
    *,
    community: str | None = None,
    dry_run: bool = False,
    skip_template_examples: bool = True,
) -> dict:
    source_file = Path(path).expanduser().resolve()
    if not source_file.exists():
        raise FileNotFoundError(f"FAQ docx not found: {source_file}")

    community_name = (community or infer_community_name(source_file)).strip() or "default"
    rows = _extract_rows(source_file)
    if skip_template_examples:
        rows = _skip_template_examples(rows)

    imported_entries = [
        _entry_from_row(row, community=community_name, source_file=source_file)
        for row in rows
    ]

    existing = load_faq_entries()
    by_id = {str(entry.get("id")): entry for entry in existing}
    created = 0
    updated = 0

    for entry in imported_entries:
        if entry["id"] in by_id:
            if by_id[entry["id"]] != entry:
                updated += 1
            by_id[entry["id"]] = entry
        else:
            created += 1
            by_id[entry["id"]] = entry

    if not dry_run:
        save_faq_entries(list(by_id.values()))

    return {
        "ok": True,
        "dry_run": dry_run,
        "file": str(source_file),
        "community": community_name,
        "skip_template_examples": skip_template_examples,
        "imported": len(imported_entries),
        "created": created,
        "updated": updated,
        "entries": imported_entries,
    }
