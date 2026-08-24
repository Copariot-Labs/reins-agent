from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable
from uuid import uuid4

from reins.features.office.content_writer import generate_office_content, reins_status
from reins.features.office.editor import (
    OfficePlanner,
    OfficeRevisionError,
    apply_revision_plan,
    build_revision_prompt,
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


def create_office_document(
    *,
    prompt: str,
    office_format: str = "docx",
    title: str | None = None,
    language: str = "zh",
    timeout: int = 180,
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
            "Reins 正在整理内容、结构和设计方案", "Reins is planning content, structure, and design",
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
        temporary.replace(source)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        shutil.copy2(backup, source)
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
user explicitly requests a visual change. Do not mention this revision process
inside the finished document.
""".strip()
    revised_content = generate_office_content(
        prompt=revision_prompt,
        office_format="docx",
        title=record.title,
        language=str(record.metadata.get("language") or "zh"),
        timeout=timeout,
        use_reins=True,
        skill_id=str(record.metadata.get("workflow_id") or "") or None,
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
        temporary.replace(source)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    metadata = dict(record.metadata)
    history = metadata.get("revisions")
    history = list(history) if isinstance(history, list) else []
    revision = {
        "revision": record.revision_count + 1,
        "instruction": instruction,
        "summary": f"Updated structured Word content: {instruction[:240]}",
        "command_count": client.command_count,
        "validation": "OfficeCLI validation passed",
        "issues": {},
    }
    history.append(revision)
    metadata.update(
        {
            "content": revised_content,
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
inside the finished workbook.
""".strip()
    revised_content = generate_office_content(
        prompt=revision_prompt,
        office_format="xlsx",
        title=record.title,
        language=str(record.metadata.get("language") or "zh"),
        timeout=timeout,
        use_reins=True,
        skill_id=str(record.metadata.get("workflow_id") or "") or None,
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
        temporary.replace(source)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    metadata = dict(record.metadata)
    history = metadata.get("revisions")
    history = list(history) if isinstance(history, list) else []
    revision = {
        "revision": record.revision_count + 1,
        "instruction": instruction,
        "summary": f"Updated structured Excel workbook: {instruction[:240]}",
        "command_count": client.command_count,
        "validation": "OfficeCLI validation passed",
        "issues": {},
    }
    history.append(revision)
    metadata.update(
        {
            "content": revised_content,
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


def revise_office_document(
    *,
    document_id: str,
    instruction: str,
    timeout: int = 180,
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
    if record.kind == "pptx" and isinstance(content, dict) and content.get("slides"):
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
    if record.kind == "docx" and record.generator == "reins" and isinstance(content, dict):
        return _revise_structured_word_document(
            record=record,
            source=source,
            instruction=clean_instruction,
            timeout=timeout,
            client=client,
            progress=progress,
        )
    if record.kind == "xlsx" and record.generator == "reins" and isinstance(content, dict):
        return _revise_structured_excel_document(
            record=record,
            source=source,
            instruction=clean_instruction,
            timeout=timeout,
            client=client,
            progress=progress,
        )

    _report_progress(
        progress, "inspection", 18,
        "OfficeCLI 正在读取原文件结构", "OfficeCLI is inspecting the original file structure",
    )
    inspection = inspect_office_document(record, client=client)

    previous_error = ""
    result: dict[str, Any] | None = None
    try:
        for attempt in range(2):
            if attempt:
                _report_progress(
                    progress, "retry", 44,
                    "正在根据验证结果调整修改方案", "Adjusting the revision plan after validation",
                )
                shutil.copy2(backup, source)
            prompt = build_revision_prompt(
                record=record,
                instruction=clean_instruction,
                inspection=inspection,
                previous_error=previous_error,
            )
            try:
                _report_progress(
                    progress, "revision_planning", 34,
                    "Reins 正在制定精确修改方案", "Reins is preparing an exact revision plan",
                )
                plan = plan_office_revision(prompt, timeout, planner=planner)
                _report_progress(
                    progress, "officecli_apply", 62,
                    "OfficeCLI 正在修改原文件并验证结果", "OfficeCLI is revising the original file and validating it",
                )
                result = apply_revision_plan(record, plan, client=client)
                _report_progress(
                    progress, "validating", 92,
                    "文件修改已通过结构和格式检查", "The revision passed structure and formatting checks",
                )
                break
            except Exception as exc:
                if _is_revision_timeout(exc):
                    raise OfficeServiceError(
                        f"Reins revision planning timed out after {timeout} seconds."
                    ) from exc
                previous_error = f"{type(exc).__name__}: {exc}"

        if result is None:
            raise OfficeRevisionError(previous_error or "Reins could not produce a valid Office revision.")
    except Exception:
        shutil.copy2(backup, source)
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
    metadata.update(
        {
            "revisions": history[-50:],
            "last_revision": history[-1],
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
