from __future__ import annotations

from collections import OrderedDict
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Callable
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from reins.features.office.content_writer import (
    DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    generate_office_content,
    reins_status,
)
from reins.features.office.editor import (
    OfficePlanner,
    OfficeRevisionError,
    apply_revision_plan,
    build_revision_prompt,
    canonicalize_excel_revision_inspection,
    canonicalize_presentation_revision_inspection,
    canonicalize_revision_plan_paths,
    canonicalize_word_revision_inspection,
    inherit_word_revision_formatting,
    compact_revision_result,
    inspect_office_document,
    plan_office_revision,
    revise_presentation_content,
)
from reins.features.office.officecli_client import OfficeCliClient, officecli_status
from reins.features.office.paths import (
    office_backups_dir,
    office_index_path,
    office_previews_dir,
    unique_office_path,
)
from reins.features.office.renderer import render_office_content
from reins.features.office.schemas import (
    OfficeDocumentRecord,
    normalize_office_format,
    normalize_presentation_options,
    normalize_title,
    utc_now_iso,
)
from reins.features.office.workflows import get_office_workflow


class OfficeServiceError(RuntimeError):
    pass


OfficeProgressReporter = Callable[[str, int, str, str], None]

_FULL_STRUCTURED_REVISION_PATTERN = re.compile(
    r"(?:"
    r"\b(?:redesign|rebrand|translate|rewrite|rebuild)\b|"
    r"\b(?:entire|whole|complete|full)\s+(?:document|workbook|presentation|deck)\b|"
    r"全文|整篇|整份|整个|全部|所有|全面|整体|彻底|重新设计|全新设计|"
    r"整体改版|统一改为|翻译|译成|改成中文|重新编写|重新生成"
    r")",
    re.IGNORECASE,
)
_INSPECTION_CACHE_MAX = 24
_inspection_cache: OrderedDict[tuple[str, int, int, str], dict[str, str]] = OrderedDict()
_inspection_cache_lock = threading.Lock()


def _report_progress(
    progress: OfficeProgressReporter | None,
    stage: str,
    percent: int,
    message_zh: str,
    message_en: str,
) -> None:
    if progress is None:
        return
    try:
        progress(stage, percent, message_zh, message_en)
    except Exception:
        pass


def _is_revision_timeout(error: Exception) -> bool:
    if isinstance(error, (subprocess.TimeoutExpired, TimeoutError)):
        return True
    return "timed out" in str(error).casefold()


def _revision_error_feedback(error: Exception) -> str:
    detail = re.sub(r"\s+", " ", f"{type(error).__name__}: {error}").strip()
    if len(detail) <= 1_600:
        return detail
    return f"{detail[:800]} ... [truncated] ... {detail[-800:]}"


def _requires_full_structured_revision(instruction: str) -> bool:
    return bool(_FULL_STRUCTURED_REVISION_PATTERN.search(instruction))


def _office_file_fingerprint(path: Path) -> tuple[str, int, int, str]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as office_file:
        for chunk in iter(lambda: office_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return (str(path.resolve()), stat.st_size, stat.st_mtime_ns, digest.hexdigest())


def _inspect_office_document_cached(
    record: OfficeDocumentRecord,
    *,
    cache_path: Path,
    client: OfficeCliClient,
) -> tuple[dict[str, str], bool]:
    key = _office_file_fingerprint(cache_path)
    with _inspection_cache_lock:
        cached = _inspection_cache.get(key)
        if cached is not None:
            _inspection_cache.move_to_end(key)
            return dict(cached), True

    inspection = inspect_office_document(record, client=client)
    with _inspection_cache_lock:
        _inspection_cache[key] = dict(inspection)
        _inspection_cache.move_to_end(key)
        while len(_inspection_cache) > _INSPECTION_CACHE_MAX:
            _inspection_cache.popitem(last=False)
    return inspection, False


_REVISION_LANGUAGE_PATTERNS = (
    ("zh", re.compile(
        r"(?:\b(?:into|to)\s+(?:simplified\s+|traditional\s+)?(?:chinese|chinse|mandarin)\b"
        r"|\b(?:chinese|chinse|mandarin)\s+(?:translation|version)\b"
        r"|(?:翻译|译|转换|改).{0,40}(?:成|为)(?:简体中文|繁体中文|中文|汉语)"
        r"|(?:需要|要|使用|用).{0,30}(?:简体中文|繁体中文|中文|汉语)(?:版|版本)?"
        r"|(?:简体中文|繁体中文|中文)(?:版|版本|翻译))",
        re.IGNORECASE,
    )),
    ("en", re.compile(
        r"(?:\b(?:into|to)\s+english\b|\benglish\s+(?:translation|version)\b"
        r"|(?:翻译|译|转换|改).{0,40}(?:成|为)(?:英文|英语)"
        r"|(?:需要|要|使用|用).{0,30}(?:英文|英语)(?:版|版本)?"
        r"|(?:英文|英语)(?:版|版本|翻译))",
        re.IGNORECASE,
    )),
    ("ja", re.compile(
        r"(?:\b(?:into|to)\s+japanese\b|\bjapanese\s+(?:translation|version)\b"
        r"|(?:翻译|译|转换|改).{0,40}(?:成|为)(?:日文|日语))",
        re.IGNORECASE,
    )),
    ("ko", re.compile(
        r"(?:\b(?:into|to)\s+korean\b|\bkorean\s+(?:translation|version)\b"
        r"|(?:翻译|译|转换|改).{0,40}(?:成|为)(?:韩文|韩语))",
        re.IGNORECASE,
    )),
)


def _revision_language(instruction: str, fallback: str) -> str:
    matches: list[tuple[int, str]] = []
    for language, pattern in _REVISION_LANGUAGE_PATTERNS:
        matches.extend((match.start(), language) for match in pattern.finditer(instruction))
    if matches:
        return max(matches, key=lambda item: item[0])[1]
    return str(fallback or "zh").strip() or "zh"


_WINDOWS_REPLACE_RETRY_DELAYS = (0.12, 0.2, 0.35, 0.55, 0.9, 1.4, 2.1)
_REVISION_PLAN_ATTEMPTS = 3
_REVISION_APPLY_RETRY_DELAYS = (0.35, 1.0)


def _is_windows_sharing_error(error: OSError) -> bool:
    if os.name != "nt":
        return False
    return getattr(error, "winerror", None) in {5, 32, 33} or error.errno in {
        errno.EACCES,
        errno.EBUSY,
    }


def _atomic_replace(source: Path, destination: Path) -> None:
    os.replace(source, destination)


def _replace_revised_file(
    temporary: Path,
    source: Path,
    *,
    progress: OfficeProgressReporter | None = None,
) -> None:
    for attempt in range(len(_WINDOWS_REPLACE_RETRY_DELAYS) + 1):
        try:
            _atomic_replace(temporary, source)
            return
        except OSError as exc:
            if not _is_windows_sharing_error(exc):
                raise
            if attempt >= len(_WINDOWS_REPLACE_RETRY_DELAYS):
                raise OfficeServiceError(
                    "The Office file is being used by another program. Close it in "
                    "Microsoft Office or the File Explorer preview pane and try again; "
                    "the original file was preserved."
                ) from exc
            if attempt == 0:
                _report_progress(
                    progress,
                    "waiting_for_file",
                    97,
                    "Windows 正在释放文件占用，Reins 将自动重试",
                    "Waiting for Windows to release the file before retrying",
                )
            time.sleep(_WINDOWS_REPLACE_RETRY_DELAYS[attempt])


def _discard_temporary_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _restore_revision_working_copy(backup: Path, working: Path) -> None:
    for attempt in range(len(_WINDOWS_REPLACE_RETRY_DELAYS) + 1):
        try:
            shutil.copy2(backup, working)
            return
        except OSError as exc:
            if (
                not _is_windows_sharing_error(exc)
                or attempt >= len(_WINDOWS_REPLACE_RETRY_DELAYS)
            ):
                raise
            time.sleep(_WINDOWS_REPLACE_RETRY_DELAYS[attempt])


def _record_at_path(record: OfficeDocumentRecord, path: Path) -> OfficeDocumentRecord:
    return OfficeDocumentRecord(
        id=record.id,
        title=record.title,
        kind=record.kind,
        path=str(path),
        file_name=path.name,
        mime_type=record.mime_type,
        created_at=record.created_at,
        updated_at=record.updated_at,
        revision_count=record.revision_count,
        prompt=record.prompt,
        generator=record.generator,
        command_count=record.command_count,
        metadata=record.metadata,
    )


def _append_record(record: OfficeDocumentRecord) -> OfficeDocumentRecord:
    index_path = office_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return record


def list_office_documents(*, limit: int = 25, kind: str | None = None) -> list[OfficeDocumentRecord]:
    index_path = office_index_path()
    if not index_path.exists():
        return []

    normalized_kind = normalize_office_format(kind) if kind else None
    records_by_id: dict[str, OfficeDocumentRecord] = {}
    with index_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                record = OfficeDocumentRecord.from_dict(json.loads(line))
            except Exception:
                continue
            if normalized_kind and record.kind != normalized_kind:
                continue
            records_by_id[record.id] = record

    records = list(records_by_id.values())

    if limit <= 0:
        return records
    return records[-limit:]


def get_office_document(document_id: str) -> OfficeDocumentRecord:
    clean_id = str(document_id or "").strip()
    if not clean_id:
        raise OfficeServiceError("Office document id is required.")
    for record in list_office_documents(limit=0):
        if record.id == clean_id:
            return record
    raise OfficeServiceError("Office document was not found.")


_OFFICE_PACKAGE_ROOTS = {
    "docx": "word/document.xml",
    "xlsx": "xl/workbook.xml",
    "pptx": "ppt/presentation.xml",
}
_MAX_OFFICE_PACKAGE_UNCOMPRESSED_SIZE = 500 * 1024 * 1024


def _import_display_name(value: object, *, office_format: str) -> str:
    raw_name = str(value or "").replace("\\", "/")
    file_name = Path(raw_name).name.strip()
    if not file_name:
        raise OfficeServiceError("Office import file name is required.")
    expected_suffix = f".{office_format}"
    if Path(file_name).suffix.lower() != expected_suffix:
        raise OfficeServiceError(
            f"The selected Office section only accepts {expected_suffix} files."
        )
    return file_name


def _validate_office_package(source: Path, office_format: str) -> None:
    expected_member = _OFFICE_PACKAGE_ROOTS[office_format]
    try:
        with ZipFile(source) as package:
            package_info = package.infolist()
            expanded_size = sum(member.file_size for member in package_info)
            if expanded_size > _MAX_OFFICE_PACKAGE_UNCOMPRESSED_SIZE:
                raise OfficeServiceError("The uploaded Office package expands beyond 500 MB.")
            members = {member.filename for member in package_info}
            if expected_member not in members:
                raise OfficeServiceError(
                    f"The uploaded file is not a valid {office_format.upper()} package."
                )
            bad_member = package.testzip()
            if bad_member:
                raise OfficeServiceError(
                    f"The uploaded Office package is damaged near {bad_member}."
                )
    except BadZipFile as exc:
        raise OfficeServiceError(
            f"The uploaded file is not a valid {office_format.upper()} package."
        ) from exc


def import_office_document(
    *,
    source_path: str | Path,
    office_format: str,
    display_name: str | None = None,
) -> OfficeDocumentRecord:
    """Register an existing Office file in the Reins workspace."""
    source = Path(source_path).expanduser()
    if not source.is_file():
        raise OfficeServiceError("The Office import file was not found.")

    normalized = normalize_office_format(office_format)
    file_name = _import_display_name(
        display_name or source.name,
        office_format=normalized,
    )
    _validate_office_package(source, normalized)

    title = normalize_title(Path(file_name).stem)
    destination = unique_office_path(title=title, office_format=normalized)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, destination)
        record = OfficeDocumentRecord.create(
            title=title,
            kind=normalized,
            path=destination,
            prompt="",
            generator="import",
            command_count=0,
            metadata={
                "imported": True,
                "source_file_name": file_name,
            },
        )
        return _append_record(record)
    except Exception:
        _discard_temporary_file(destination)
        raise


def create_office_document(
    *,
    prompt: str,
    office_format: str = "docx",
    title: str | None = None,
    language: str = "zh",
    timeout: int = DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    use_reins: bool = True,
    presentation_options: dict[str, Any] | None = None,
    skill_id: str | None = None,
    content: dict[str, Any] | None = None,
    client: OfficeCliClient | None = None,
    progress: OfficeProgressReporter | None = None,
) -> OfficeDocumentRecord:
    _report_progress(progress, "accepted", 4, "已接收文件生成请求", "Document request received")
    cleaned_prompt = str(prompt or "").strip()
    if not cleaned_prompt and content is None:
        raise OfficeServiceError("Office prompt is required.")

    normalized = normalize_office_format(office_format)
    workflow = (
        get_office_workflow(skill_id, office_format=normalized)
        if skill_id
        else None
    )
    _report_progress(
        progress, "skill_ready", 10,
        "已读取文档技能和生成要求", "Document skill and requirements loaded",
    )
    normalized_presentation_options = normalize_presentation_options(presentation_options)
    if content is None:
        _report_progress(
            progress, "content_generation", 18,
            "Reins 正在整理内容、结构和设计方案，生成需要一些时间，请耐心等待",
            "Reins is planning content, structure, and design. Generation can take some time; please wait while Reins continues processing",
        )
    content_payload = content or generate_office_content(
        prompt=cleaned_prompt,
        office_format=normalized,
        title=title,
        language=language,
        timeout=timeout,
        use_reins=use_reins,
        presentation_options=normalized_presentation_options,
        skill_id=skill_id,
    )
    _report_progress(
        progress, "content_ready", 49,
        "内容与版式方案已完成", "Content and layout plan completed",
    )

    document_title = normalize_title(content_payload.get("title") or title)
    output_path = unique_office_path(title=document_title, office_format=normalized)
    client = client or OfficeCliClient()

    path = render_office_content(
        office_format=normalized,
        content=content_payload,
        output_path=output_path,
        client=client,
        progress=progress,
    )

    _report_progress(
        progress, "saving", 98,
        "正在保存文件记录", "Saving the document record",
    )
    record = _append_record(
        OfficeDocumentRecord.create(
            title=document_title,
            kind=normalized,
            path=path,
            prompt=cleaned_prompt,
            generator=str(content_payload.get("generator") or "reins"),
            command_count=client.command_count,
            metadata={
                "language": language,
                "document_kind": content_payload.get("document_kind"),
                "missing_fields": content_payload.get("missing_fields", []),
                "generator_error": content_payload.get("generator_error"),
                "workflow_id": workflow.id if workflow else None,
                "presentation_options": (
                    normalized_presentation_options if normalized == "pptx" else None
                ),
                "content": content_payload,
            },
        )
    )
    _report_progress(progress, "completed", 100, "文件生成完成", "Document created")
    return record


def office_status() -> dict[str, object]:
    status = officecli_status()
    brain = reins_status()
    status["reins_available"] = brain["available"]
    status["reins_command"] = brain["command"]
    status["documents"] = len(list_office_documents(limit=0))
    status["index_path"] = str(office_index_path())
    return status


def preview_office_document(
    document_id: str,
    *,
    client: OfficeCliClient | None = None,
) -> Path:
    record = get_office_document(document_id)
    source = Path(record.path)
    if not source.exists():
        raise OfficeServiceError(f"Office file no longer exists: {source}")

    preview_path = office_previews_dir() / f"{record.id}.html"
    if preview_path.exists() and preview_path.stat().st_mtime_ns >= source.stat().st_mtime_ns:
        return preview_path

    client = client or OfficeCliClient()
    client.run(
        ["view", source, "html", "-o", preview_path],
        timeout=120,
        env_overrides={"OFFICECLI_NO_AUTO_RESIDENT": "1"},
    )
    if not preview_path.exists():
        raise OfficeServiceError("Reins Office did not create the preview.")
    return preview_path


def _revise_structured_presentation(
    *,
    record: OfficeDocumentRecord,
    source: Path,
    backup: Path,
    instruction: str,
    timeout: int,
    client: OfficeCliClient,
    planner: OfficePlanner | None,
    progress: OfficeProgressReporter | None,
) -> OfficeDocumentRecord:
    temporary = source.with_name(f".{source.stem}-revision-{uuid4().hex}.pptx")
    try:
        _report_progress(
            progress, "revision_planning", 24,
            "Reins 正在分析修改要求并重新设计演示文稿", "Reins is analyzing the revision and redesigning the presentation",
        )
        revision_plan = revise_presentation_content(
            record=record,
            instruction=instruction,
            timeout=timeout,
            planner=planner,
        )
        content = revision_plan["content"]
        render_office_content(
            office_format="pptx",
            content=content,
            output_path=temporary,
            client=client,
            progress=progress,
        )
        _replace_revised_file(temporary, source, progress=progress)
    except Exception:
        _discard_temporary_file(temporary)
        if not source.exists():
            try:
                shutil.copy2(backup, source)
            except OSError:
                pass
        raise

    revision = {
        "summary": str(revision_plan.get("summary") or "Presentation updated"),
        "command_count": client.command_count,
        "validation": "Reins Office validation and layout checks passed.",
        "issues": {"count": 0, "issues": []},
    }
    metadata = dict(record.metadata)
    history = metadata.get("revisions")
    history = list(history) if isinstance(history, list) else []
    history.append(
        {
            "revision": record.revision_count + 1,
            "instruction": instruction,
            **revision,
        }
    )
    metadata.update(
        {
            "content": revision_plan["content"],
            "revisions": history[-50:],
            "last_revision": history[-1],
        }
    )

    updated = OfficeDocumentRecord(
        id=record.id,
        title=normalize_title(revision_plan["content"].get("title") or record.title),
        kind=record.kind,
        path=record.path,
        file_name=record.file_name,
        mime_type=record.mime_type,
        created_at=record.created_at,
        updated_at=utc_now_iso(),
        revision_count=record.revision_count + 1,
        prompt=record.prompt,
        generator="reins",
        command_count=record.command_count + client.command_count,
        metadata=metadata,
    )
    _report_progress(progress, "saving", 98, "正在保存修改记录", "Saving the revision record")
    saved = _append_record(updated)
    _report_progress(progress, "completed", 100, "文件修改完成", "Document revision completed")
    return saved


def _revise_structured_word_document(
    *,
    record: OfficeDocumentRecord,
    source: Path,
    instruction: str,
    timeout: int,
    client: OfficeCliClient,
    progress: OfficeProgressReporter | None,
) -> OfficeDocumentRecord:
    current = record.metadata.get("content")
    if not isinstance(current, dict):
        raise OfficeServiceError("This Word document does not have editable Reins content metadata.")
    revision_language = _revision_language(
        instruction,
        str(record.metadata.get("language") or "zh"),
    )

    _report_progress(
        progress, "revision_planning", 24,
        "Reins 正在根据原文重新整理修改后的内容", "Reins is revising the saved document structure",
    )
    revision_prompt = f"""
Revise the existing Word document according to the user's instruction.

User instruction:
{instruction}

Current structured document content:
{json.dumps(current, ensure_ascii=False)}

Return the complete revised Word document content, not a patch. Preserve all
unrelated facts, sections, tables, and design choices. Apply the instruction
consistently everywhere it is relevant. Preserve the current design unless the
user explicitly requests a visual change. When a design change is requested,
Reins must choose a suitable complete design from the current content and the
new instruction. The original creation skill is provenance, not a constraint on
this revision. Do not mention this revision process inside the finished document.
""".strip()
    revised_content = generate_office_content(
        prompt=revision_prompt,
        office_format="docx",
        title=record.title,
        language=revision_language,
        timeout=timeout,
        use_reins=True,
    )
    if revised_content.get("generator") != "reins":
        raise OfficeServiceError(
            "Reins did not return a valid structured Word revision; the original file was preserved."
        )
    _report_progress(
        progress, "content_ready", 52,
        "修改后的内容和版式方案已完成", "The revised content and layout are ready",
    )

    temporary = source.with_name(f".{source.stem}-revision-{uuid4().hex}.docx")
    try:
        render_office_content(
            office_format="docx",
            content=revised_content,
            output_path=temporary,
            client=client,
            progress=progress,
        )
        _replace_revised_file(temporary, source, progress=progress)
    except Exception:
        _discard_temporary_file(temporary)
        raise

    metadata = dict(record.metadata)
    history = metadata.get("revisions")
    history = list(history) if isinstance(history, list) else []
    revision = {
        "revision": record.revision_count + 1,
        "instruction": instruction,
        "summary": f"更新内容: {instruction[:240]}",
        "command_count": client.command_count,
        "validation": "OfficeCLI validation passed",
        "issues": {},
    }
    history.append(revision)
    metadata.update(
        {
            "content": revised_content,
            "language": revision_language,
            "document_kind": revised_content.get("document_kind"),
            "missing_fields": revised_content.get("missing_fields", []),
            "generator_error": revised_content.get("generator_error"),
            "revisions": history[-50:],
            "last_revision": history[-1],
        }
    )

    updated = OfficeDocumentRecord(
        id=record.id,
        title=normalize_title(revised_content.get("title") or record.title),
        kind=record.kind,
        path=record.path,
        file_name=record.file_name,
        mime_type=record.mime_type,
        created_at=record.created_at,
        updated_at=utc_now_iso(),
        revision_count=record.revision_count + 1,
        prompt=record.prompt,
        generator="reins",
        command_count=record.command_count + client.command_count,
        metadata=metadata,
    )
    _report_progress(progress, "saving", 98, "正在保存修改记录", "Saving the revision record")
    saved = _append_record(updated)
    _report_progress(progress, "completed", 100, "文件修改完成", "Document revision completed")
    return saved


def _revise_structured_excel_document(
    *,
    record: OfficeDocumentRecord,
    source: Path,
    instruction: str,
    timeout: int,
    client: OfficeCliClient,
    progress: OfficeProgressReporter | None,
) -> OfficeDocumentRecord:
    current = record.metadata.get("content")
    if not isinstance(current, dict) or not isinstance(current.get("sheets"), list):
        raise OfficeServiceError("This Excel workbook does not have editable Reins content metadata.")
    revision_language = _revision_language(
        instruction,
        str(record.metadata.get("language") or "zh"),
    )

    _report_progress(
        progress, "revision_planning", 24,
        "Reins 正在根据原工作簿重新整理数据和设计", "Reins is revising the saved workbook structure and design",
    )
    revision_prompt = f"""
Revise the existing Excel workbook according to the user's instruction.

User instruction:
{instruction}

Current structured workbook content:
{json.dumps(current, ensure_ascii=False)}

Return the complete revised Excel workbook content, not a patch or OfficeCLI
commands. Preserve every unrelated sheet, row, value, format, highlight, and
design choice. Apply the requested changes consistently to all relevant cells.
If the user requests a design change, choose a suitable complete workbook
design; otherwise preserve the current design. Keep long explanatory text
concise enough for readable wrapped cells. Do not mention the revision process
inside the finished workbook. The original creation skill is provenance, not a
constraint on this revision.
""".strip()
    revised_content = generate_office_content(
        prompt=revision_prompt,
        office_format="xlsx",
        title=record.title,
        language=revision_language,
        timeout=timeout,
        use_reins=True,
    )
    if revised_content.get("generator") != "reins" or not revised_content.get("sheets"):
        raise OfficeServiceError(
            "Reins did not return a valid structured Excel revision; the original file was preserved."
        )
    _report_progress(
        progress, "content_ready", 52,
        "修改后的数据和版式方案已完成", "The revised workbook data and layout are ready",
    )

    temporary = source.with_name(f".{source.stem}-revision-{uuid4().hex}.xlsx")
    try:
        render_office_content(
            office_format="xlsx",
            content=revised_content,
            output_path=temporary,
            client=client,
            progress=progress,
        )
        _replace_revised_file(temporary, source, progress=progress)
    except Exception:
        _discard_temporary_file(temporary)
        raise

    metadata = dict(record.metadata)
    history = metadata.get("revisions")
    history = list(history) if isinstance(history, list) else []
    revision = {
        "revision": record.revision_count + 1,
        "instruction": instruction,
        "summary": f"更新内容: {instruction[:240]}",
        "command_count": client.command_count,
        "validation": "OfficeCLI validation passed",
        "issues": {},
    }
    history.append(revision)
    metadata.update(
        {
            "content": revised_content,
            "language": revision_language,
            "document_kind": revised_content.get("document_kind"),
            "missing_fields": revised_content.get("missing_fields", []),
            "generator_error": revised_content.get("generator_error"),
            "revisions": history[-50:],
            "last_revision": history[-1],
        }
    )

    updated = OfficeDocumentRecord(
        id=record.id,
        title=normalize_title(revised_content.get("title") or record.title),
        kind=record.kind,
        path=record.path,
        file_name=record.file_name,
        mime_type=record.mime_type,
        created_at=record.created_at,
        updated_at=utc_now_iso(),
        revision_count=record.revision_count + 1,
        prompt=record.prompt,
        generator="reins",
        command_count=record.command_count + client.command_count,
        metadata=metadata,
    )
    _report_progress(progress, "saving", 98, "正在保存修改记录", "Saving the revision record")
    saved = _append_record(updated)
    _report_progress(progress, "completed", 100, "文件修改完成", "Workbook revision completed")
    return saved


def _rebuild_revision_from_inspection(
    *,
    record: OfficeDocumentRecord,
    source: Path,
    instruction: str,
    inspection: dict[str, str],
    revision_errors: list[str],
    timeout: int,
    client: OfficeCliClient,
    progress: OfficeProgressReporter | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = record.metadata.get("content")
    inspection_context = f"""
Current OfficeCLI outline:
{inspection.get("outline") or "(empty)"}

Current OfficeCLI annotated visible content:
{inspection.get("text") or "(empty)"}

Current OfficeCLI editable elements and formatting:
{inspection.get("elements") or inspection.get("formatting") or "(not available)"}
""".strip()
    if isinstance(current, dict):
        source_context = (
            "Saved Reins structured content:\n"
            f"{json.dumps(current, ensure_ascii=False)}\n\n"
            f"{inspection_context}"
        )
    else:
        source_context = inspection_context

    _report_progress(
        progress,
        "compatibility_rebuild",
        72,
        "局部修改未能通过验证，Reins 正在自动重建兼容文件",
        "The patch could not be validated; Reins is rebuilding a compatible file",
    )
    rebuild_prompt = f"""
Rebuild the complete existing {record.kind.upper()} file after direct OfficeCLI
patch attempts could not be validated.

User instruction:
{instruction}

Existing file title:
{record.title}

Existing file content:
{source_context}

Patch failures already handled internally:
{chr(10).join(revision_errors)}

Return the complete revised file content, not a patch and not OfficeCLI commands.
Apply the user's instruction while preserving all unrelated visible content,
facts, ordering, tables, sheets, slides, and design choices represented above.
When saved structured content and the current OfficeCLI inspection differ,
the current OfficeCLI inspection is the source of truth.
Use a conservative, compatible layout. Do not mention recovery, errors, or this
prompt in the finished file. Produce the result now without asking the user to retry.
""".strip()
    language = _revision_language(
        instruction,
        str(record.metadata.get("language") or "zh"),
    )
    revised_content = generate_office_content(
        prompt=rebuild_prompt,
        office_format=record.kind,
        title=record.title,
        language=language,
        timeout=timeout,
        use_reins=True,
        presentation_options=(
            record.metadata.get("presentation_options")
            if record.kind == "pptx"
            else None
        ),
    )
    has_content = {
        "docx": bool(revised_content.get("body") or revised_content.get("tables")),
        "xlsx": bool(revised_content.get("sheets")),
        "pptx": bool(revised_content.get("slides")),
    }.get(record.kind, False)
    if revised_content.get("generator") != "reins" or not has_content:
        raise OfficeRevisionError(
            "Reins could not produce a complete compatibility rebuild."
        )

    temporary = source.with_name(
        f".reins-office-rebuild-{uuid4().hex}.{record.kind}"
    )
    try:
        render_office_content(
            office_format=record.kind,
            content=revised_content,
            output_path=temporary,
            client=client,
            progress=progress,
        )
        _replace_revised_file(temporary, source, progress=progress)
    except Exception:
        _discard_temporary_file(temporary)
        raise

    _report_progress(
        progress,
        "compatibility_ready",
        94,
        "兼容文件已重建并通过验证",
        "The compatible file was rebuilt and validated",
    )
    return revised_content, {
        "summary": f"更新内容: {instruction[:240]}",
        "commands": [],
        "validation": "Reins Office compatibility rebuild passed validation.",
        "issues": '{"count":0,"issues":[]}',
    }


def revise_office_document(
    *,
    document_id: str,
    instruction: str,
    timeout: int = DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    client: OfficeCliClient | None = None,
    planner: OfficePlanner | None = None,
    progress: OfficeProgressReporter | None = None,
) -> OfficeDocumentRecord:
    _report_progress(progress, "accepted", 4, "已接收文件修改请求", "Revision request received")
    clean_instruction = str(instruction or "").strip()
    if not clean_instruction:
        raise OfficeServiceError("Office revision instruction is required.")

    record = get_office_document(document_id)
    source = Path(record.path)
    if not source.exists():
        raise OfficeServiceError(f"Office file no longer exists: {source}")

    client = client or OfficeCliClient()
    _report_progress(
        progress, "backup", 10,
        "正在备份原文件，修改将保留在同一文件中", "Backing up the original before in-place revision",
    )
    backup = office_backups_dir() / f"{record.id}-revision-{record.revision_count + 1}.{record.kind}"
    shutil.copy2(source, backup)

    content = record.metadata.get("content")
    use_full_structured_revision = (
        not bool(record.metadata.get("content_stale"))
        and _requires_full_structured_revision(clean_instruction)
    )
    if (
        use_full_structured_revision
        and record.kind == "pptx"
        and isinstance(content, dict)
        and content.get("slides")
    ):
        return _revise_structured_presentation(
            record=record,
            source=source,
            backup=backup,
            instruction=clean_instruction,
            timeout=timeout,
            client=client,
            planner=planner,
            progress=progress,
        )
    if (
        use_full_structured_revision
        and record.kind == "docx"
        and record.generator == "reins"
        and isinstance(content, dict)
    ):
        return _revise_structured_word_document(
            record=record,
            source=source,
            instruction=clean_instruction,
            timeout=timeout,
            client=client,
            progress=progress,
        )
    if (
        use_full_structured_revision
        and record.kind == "xlsx"
        and record.generator == "reins"
        and isinstance(content, dict)
    ):
        return _revise_structured_excel_document(
            record=record,
            source=source,
            instruction=clean_instruction,
            timeout=timeout,
            client=client,
            progress=progress,
        )

    working = source.with_name(f".reins-office-revision-{uuid4().hex}.{record.kind}")
    shutil.copy2(source, working)
    working_record = _record_at_path(record, working)
    revision_errors: list[str] = []
    result: dict[str, Any] | None = None
    rebuilt_content: dict[str, Any] | None = None
    try:
        _report_progress(
            progress, "inspection", 18,
            "OfficeCLI 正在读取原文件结构", "OfficeCLI is inspecting the original file structure",
        )
        inspection, inspection_cached = _inspect_office_document_cached(
            working_record,
            cache_path=source,
            client=client,
        )
        if inspection_cached:
            _report_progress(
                progress,
                "inspection_cached",
                24,
                "已复用当前文件的结构索引",
                "Reused the current file structure index",
            )
        revision_path_aliases: dict[str, str] = {}
        if record.kind == "docx":
            inspection, revision_path_aliases = canonicalize_word_revision_inspection(
                inspection
            )
        elif record.kind == "xlsx":
            inspection, revision_path_aliases = canonicalize_excel_revision_inspection(
                inspection
            )
        elif record.kind == "pptx":
            inspection, revision_path_aliases = (
                canonicalize_presentation_revision_inspection(inspection)
            )

        for attempt in range(_REVISION_PLAN_ATTEMPTS):
            if attempt:
                _report_progress(
                    progress, "retry", 44,
                    "正在根据验证结果调整修改方案", "Adjusting the revision plan after validation",
                )
                _restore_revision_working_copy(backup, working)
            prompt = build_revision_prompt(
                record=record,
                instruction=clean_instruction,
                inspection=inspection,
                previous_error="\n".join(
                    f"Attempt {index}: {error}"
                    for index, error in enumerate(revision_errors, start=1)
                ),
            )
            _report_progress(
                progress, "revision_planning", 34,
                "Reins 正在制定精确修改方案", "Reins is preparing an exact revision plan",
            )
            try:
                plan = plan_office_revision(
                    prompt,
                    timeout,
                    planner=planner,
                    office_format=record.kind,
                )
                plan = canonicalize_revision_plan_paths(plan, revision_path_aliases)
                if record.kind == "docx":
                    plan = inherit_word_revision_formatting(plan, inspection)
            except Exception as exc:
                if _is_revision_timeout(exc):
                    raise OfficeServiceError(
                        f"Reins revision planning timed out after {timeout} seconds."
                    ) from exc
                revision_errors.append(_revision_error_feedback(exc))
                continue

            try:
                _report_progress(
                    progress, "officecli_apply", 62,
                    "OfficeCLI 正在修改原文件并验证结果", "OfficeCLI is revising the original file and validating it",
                )
                result = apply_revision_plan(working_record, plan, client=client)
                _report_progress(
                    progress, "validating", 92,
                    "文件修改已通过结构和格式检查", "The revision passed structure and formatting checks",
                )
                break
            except Exception as exc:
                revision_errors.append(_revision_error_feedback(exc))
                if attempt < len(_REVISION_APPLY_RETRY_DELAYS):
                    time.sleep(_REVISION_APPLY_RETRY_DELAYS[attempt])

        if result is None:
            _discard_temporary_file(working)
            rebuilt_content, result = _rebuild_revision_from_inspection(
                record=record,
                source=source,
                instruction=clean_instruction,
                inspection=inspection,
                revision_errors=revision_errors,
                timeout=timeout,
                client=client,
                progress=progress,
            )
        else:
            _replace_revised_file(working, source, progress=progress)
    except Exception:
        _discard_temporary_file(working)
        if not source.exists():
            try:
                shutil.copy2(backup, source)
            except OSError:
                pass
        raise

    revision = compact_revision_result(result)
    metadata = dict(record.metadata)
    history = metadata.get("revisions")
    history = list(history) if isinstance(history, list) else []
    history.append(
        {
            "revision": record.revision_count + 1,
            "instruction": clean_instruction,
            **revision,
        }
    )
    metadata.update({"revisions": history[-50:], "last_revision": history[-1]})
    if rebuilt_content is not None:
        metadata.update(
            {
                "content": rebuilt_content,
                "language": _revision_language(
                    clean_instruction,
                    str(metadata.get("language") or "zh"),
                ),
                "document_kind": rebuilt_content.get("document_kind"),
                "missing_fields": rebuilt_content.get("missing_fields", []),
                "generator_error": rebuilt_content.get("generator_error"),
                "content_stale": False,
                "revision_mode": "officecli_rebuild_recovery",
            }
        )
    else:
        metadata.update(
            {
                "content_stale": isinstance(metadata.get("content"), dict),
                "revision_mode": "officecli_patch",
            }
        )

    updated = OfficeDocumentRecord(
        id=record.id,
        title=record.title,
        kind=record.kind,
        path=record.path,
        file_name=record.file_name,
        mime_type=record.mime_type,
        created_at=record.created_at,
        updated_at=utc_now_iso(),
        revision_count=record.revision_count + 1,
        prompt=record.prompt,
        generator="reins",
        command_count=record.command_count + client.command_count,
        metadata=metadata,
    )
    _report_progress(progress, "saving", 98, "正在保存修改记录", "Saving the revision record")
    saved = _append_record(updated)
    _report_progress(progress, "completed", 100, "文件修改完成", "Document revision completed")
    return saved
