from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any
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


class OfficeServiceError(RuntimeError):
    pass


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
    language: str = "en",
    timeout: int = 180,
    use_reins: bool = True,
    presentation_options: dict[str, Any] | None = None,
    content: dict[str, Any] | None = None,
    client: OfficeCliClient | None = None,
) -> OfficeDocumentRecord:
    cleaned_prompt = str(prompt or "").strip()
    if not cleaned_prompt and content is None:
        raise OfficeServiceError("Office prompt is required.")

    normalized = normalize_office_format(office_format)
    normalized_presentation_options = normalize_presentation_options(presentation_options)
    content_payload = content or generate_office_content(
        prompt=cleaned_prompt,
        office_format=normalized,
        title=title,
        language=language,
        timeout=timeout,
        use_reins=use_reins,
        presentation_options=normalized_presentation_options,
    )

    document_title = normalize_title(content_payload.get("title") or title)
    output_path = unique_office_path(title=document_title, office_format=normalized)
    client = client or OfficeCliClient()

    path = render_office_content(
        office_format=normalized,
        content=content_payload,
        output_path=output_path,
        client=client,
    )

    return _append_record(
        OfficeDocumentRecord.create(
            title=document_title,
            kind=normalized,
            path=path,
            prompt=cleaned_prompt,
            generator=str(content_payload.get("generator") or "reins"),
            officecli_bin=client.binary,
            command_count=client.command_count,
            metadata={
                "language": language,
                "document_kind": content_payload.get("document_kind"),
                "missing_fields": content_payload.get("missing_fields", []),
                "generator_error": content_payload.get("generator_error"),
                "presentation_options": (
                    normalized_presentation_options if normalized == "pptx" else None
                ),
                "content": content_payload,
            },
        )
    )


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
        raise OfficeServiceError("OfficeCLI did not create the HTML preview.")
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
) -> OfficeDocumentRecord:
    temporary = source.with_name(f".{source.stem}-revision-{uuid4().hex}.pptx")
    try:
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
        "validation": "OfficeCLI validation and layout checks passed.",
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
        officecli_bin=client.binary,
        command_count=record.command_count + client.command_count,
        metadata=metadata,
    )
    return _append_record(updated)


def revise_office_document(
    *,
    document_id: str,
    instruction: str,
    timeout: int = 180,
    client: OfficeCliClient | None = None,
    planner: OfficePlanner | None = None,
) -> OfficeDocumentRecord:
    clean_instruction = str(instruction or "").strip()
    if not clean_instruction:
        raise OfficeServiceError("Office revision instruction is required.")

    record = get_office_document(document_id)
    source = Path(record.path)
    if not source.exists():
        raise OfficeServiceError(f"Office file no longer exists: {source}")

    client = client or OfficeCliClient()
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
        )

    inspection = inspect_office_document(record, client=client)

    previous_error = ""
    result: dict[str, Any] | None = None
    try:
        for attempt in range(2):
            if attempt:
                shutil.copy2(backup, source)
            prompt = build_revision_prompt(
                record=record,
                instruction=clean_instruction,
                inspection=inspection,
                previous_error=previous_error,
            )
            try:
                plan = plan_office_revision(prompt, timeout, planner=planner)
                result = apply_revision_plan(record, plan, client=client)
                break
            except Exception as exc:
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
        officecli_bin=client.binary,
        command_count=record.command_count + client.command_count,
        metadata=metadata,
    )
    return _append_record(updated)
