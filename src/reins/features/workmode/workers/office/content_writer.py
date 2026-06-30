from __future__ import annotations

import json
import re
from typing import Any

from reins.features.workmode.artifacts import infer_office_artifact_format, normalize_office_format
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.vendor_hermes import call_vendor_hermes_json


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _format_sources(state: WorkExecutionState) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    for source in state.sources:
        if not isinstance(source, dict):
            continue

        sources.append(
            {
                "title": source.get("title"),
                "url": source.get("url"),
                "summary": source.get("summary"),
                "key_facts": source.get("key_facts"),
                "screenshot": source.get("screenshot"),
                "html": source.get("html"),
            }
        )

    return sources


def _format_previous_outputs(state: WorkExecutionState) -> list[Any]:
    previous_outputs = state.scratch.get("previous_outputs")

    if isinstance(previous_outputs, list):
        return previous_outputs

    return []


def _fallback_title(step: WorkStep, state: WorkExecutionState) -> str:
    for key in ("document_title", "report_title", "title"):
        value = _clean_text(step.metadata.get(key))
        if value:
            return value

    document_kind = _infer_document_kind(step, state)
    topic = _topic_from_message(state.message)

    if document_kind == "notice":
        return f"Resident Notice: {topic}" if topic else "Resident Notice"

    if document_kind == "application":
        return f"Application: {topic}" if topic else "Application"

    if document_kind == "memo":
        return f"Memo: {topic}" if topic else "Memo"

    if document_kind == "presentation":
        return f"Presentation: {topic}" if topic else "WorkMode Presentation"

    if document_kind in {"ledger", "spreadsheet"}:
        return f"{topic} Ledger" if topic else "WorkMode Ledger"

    if document_kind == "report":
        return f"Report: {topic}" if topic else "WorkMode Report"

    return topic or "WorkMode Document"


def _strip_action_prefix(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip(" .")
    lower = cleaned.lower()

    prefixes = (
        "please ",
        "can you ",
        "could you ",
        "write ",
        "create ",
        "generate ",
        "make ",
        "prepare ",
        "draft ",
        "build ",
        "produce ",
    )

    changed = True
    while changed:
        changed = False
        lower = cleaned.lower()
        for prefix in prefixes:
            if lower.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip(" .")
                changed = True
                break

    return cleaned


def _topic_from_message(message: str) -> str:
    text = _strip_action_prefix(message)
    text = re.sub(
        r"^(a|an|the)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(
        r"^(resident\s+)?(notice|report|memo|letter|application|document|presentation|slides?|powerpoint|excel|spreadsheet|workbook|ledger)\b[:,]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = re.sub(r"^(about|for|regarding|on)\s+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\b(notice|report|memo|letter|application|document)\b", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(about|for|regarding|on)\s+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"^(a|an|the)\s+", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text).strip(" ,.-")

    if not text:
        return "Requested Office Artifact"

    return " ".join(word.capitalize() if word.islower() else word for word in text.split()[:12])


def _infer_document_kind(step: WorkStep, state: WorkExecutionState) -> str:
    metadata_kind = _clean_text(step.metadata.get("document_kind"))
    if metadata_kind:
        return metadata_kind.lower()

    text = " ".join([state.message, step.title, " ".join(map(str, step.expected_artifacts))]).lower()
    artifact_format = infer_office_artifact_format(state.message, step.metadata, step.expected_artifacts)

    if artifact_format == "pptx":
        return "presentation"
    if artifact_format == "xlsx":
        return "ledger" if "ledger" in text or "台账" in text else "spreadsheet"
    if "notice" in text or "通知" in text:
        return "notice"
    if "application" in text or "申请" in text:
        return "application"
    if "memo" in text:
        return "memo"
    if "letter" in text:
        return "letter"
    if "report" in text or "报告" in text:
        return "report"
    return "other"


def _fallback_notice_body(title: str, topic: str) -> str:
    return "\n\n".join(
        [
            title,
            "[Date]",
            "Dear Residents,",
            (
                f"We would like to share the following notice regarding {topic}. "
                "Please review the information below and make any necessary arrangements."
            ),
            (
                "During this period, residents are kindly reminded to keep shared corridors "
                "and public areas clear, follow community safety requirements, dispose of "
                "waste properly, and be considerate of neighbors."
            ),
            (
                "If there are changes to office hours, access arrangements, maintenance "
                "service schedules, parcel collection, parking, or visitor registration, "
                "please refer to the latest notice from the property management office."
            ),
            (
                "For urgent matters, please contact [Property Management Contact]. "
                "Thank you for your understanding and cooperation."
            ),
            "Property Management Office",
        ]
    )


def _fallback_application_body(title: str, topic: str) -> str:
    return "\n\n".join(
        [
            title,
            "[Date]",
            "To: [Recipient Name / Department]",
            "Dear [Recipient Name],",
            (
                f"I am writing to submit this application regarding {topic}. "
                "Please find the relevant details below for your review."
            ),
            "Reason / Background:\n[Describe the reason, context, and requested arrangement.]",
            "Requested Action:\n[Describe exactly what approval, support, or arrangement is requested.]",
            "Thank you for your time and consideration.",
            "Sincerely,\n[Your Name]",
        ]
    )


def _fallback_report_body(title: str, topic: str, state: WorkExecutionState) -> str:
    lines = [
        title,
        "",
        "Executive Summary",
        f"This report summarizes the available information regarding {topic}.",
        "",
        "Key Points",
        "- [Key point 1]",
        "- [Key point 2]",
        "- [Key point 3]",
        "",
        "Recommended Next Steps",
        "1. Confirm any missing dates, names, amounts, or policy references.",
        "2. Review the draft with the responsible staff member.",
        "3. Save the approved version with the case record.",
    ]

    if state.sources:
        lines.extend(["", "Source Notes"])
        for index, source in enumerate(state.sources, start=1):
            if isinstance(source, dict):
                lines.append(f"{index}. {source.get('title') or source.get('url') or 'Source'}")
                if source.get("summary"):
                    lines.append(f"   {source['summary']}")

    return "\n".join(lines)


def _fallback_generic_body(title: str, topic: str) -> str:
    return "\n\n".join(
        [
            title,
            "[Date]",
            f"This document has been prepared regarding {topic}.",
            "Background:\n[Add relevant background details here.]",
            "Main Content:\n[Add the detailed content, requirements, or explanation here.]",
            "Next Steps:\n[Add any required follow-up actions here.]",
        ]
    )


def _fallback_sheets(title: str, topic: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "Tracking",
            "columns": ["Item", "Description", "Responsible Party", "Due Date", "Status", "Notes"],
            "rows": [
                [1, f"Confirm scope for {topic}", "[Name]", "[Date]", "Pending", ""],
                [2, "Collect supporting details", "[Name]", "[Date]", "Pending", ""],
                [3, "Review and update record", "[Name]", "[Date]", "Pending", ""],
            ],
        }
    ]


def _fallback_slides(title: str, topic: str) -> list[dict[str, Any]]:
    return [
        {
            "title": title,
            "subtitle": "[Date] | Prepared for resident/community review",
            "bullets": [],
        },
        {
            "title": "Purpose",
            "bullets": [
                f"Provide a clear overview of {topic}.",
                "Share important details with residents or staff.",
                "Identify required follow-up actions.",
            ],
        },
        {
            "title": "Key Information",
            "bullets": [
                "[Important date or period]",
                "[Affected residents, facilities, or services]",
                "[Main reminder or requirement]",
            ],
        },
        {
            "title": "Resident Reminders",
            "bullets": [
                "Keep public areas safe and accessible.",
                "Follow posted community rules and service updates.",
                "Contact property management for urgent support.",
            ],
        },
        {
            "title": "Next Steps",
            "bullets": [
                "Confirm missing operational details.",
                "Publish the approved notice or deck.",
                "Save the final artifact with the WorkMode case record.",
            ],
        },
    ]


def _fallback_body(step: WorkStep, state: WorkExecutionState) -> str:
    """
    Safe fallback only.

    This should not be the normal path. The normal path should use Hermes-backed
    content writing and produce the requested document body.
    """

    title = _fallback_title(step, state)
    topic = _topic_from_message(state.message)
    document_kind = _infer_document_kind(step, state)

    if document_kind == "notice":
        body = _fallback_notice_body(title, topic)
    elif document_kind == "application":
        body = _fallback_application_body(title, topic)
    elif document_kind == "report":
        body = _fallback_report_body(title, topic, state)
    else:
        body = _fallback_generic_body(title, topic)

    lines = [body]

    if state.sources:
        lines.extend(["", "Sources:"])

        for index, source in enumerate(state.sources, start=1):
            if not isinstance(source, dict):
                continue

            title = source.get("title") or "Untitled source"
            url = source.get("url") or ""
            summary = source.get("summary") or ""

            lines.append(f"{index}. {title}")

            if url:
                lines.append(f"   URL: {url}")

            if summary:
                lines.append(f"   Summary: {summary}")

    return "\n".join(lines)


def _build_content_prompt(step: WorkStep, state: WorkExecutionState) -> str:
    intake = state.scratch.get("intake")
    research_summary = state.scratch.get("research_summary")
    artifact_format = infer_office_artifact_format(
        state.message,
        step.metadata,
        step.expected_artifacts,
        step.title,
        step.description,
    )

    return f"""
You are the backend document writer for Reins WorkMode.

The user requested an Office artifact such as a Word document, Excel workbook, PowerPoint deck, written output, application, report, letter, memo, notice, form text, table, ledger, or presentation.

Write the actual final artifact content the user asked for.

Rules:
- Do not write a WorkMode audit log.
- Do not explain the process.
- Do not include "Operator Notes" unless the user asked for handoff/operator notes.
- Do not output markdown fences.
- Do not invent private personal facts.
- If important details are missing, use professional placeholders like [Your Name], [Company Name], [Date], [Reason], [Recipient Name].
- If sources are provided, use them when relevant.
- artifact_format must be exactly "{artifact_format}" unless the user explicitly requested another Office format.
- For docx, body must be ready to place into a Word document.
- For xlsx, include sheets with columns and rows. Keep rows business-usable, not prose-only.
- For pptx, include slides with titles and concise bullets.
- Return JSON only.

Required JSON shape:
{{
  "title": "short document title",
  "artifact_format": "docx|xlsx|pptx",
  "body": "complete prose body or summary of the artifact",
  "document_kind": "letter|application|report|memo|notice|form|summary|ledger|spreadsheet|presentation|other",
  "missing_fields": ["field names that need user input"],
  "sheets": [
    {{
      "name": "short sheet name",
      "columns": ["Column A", "Column B"],
      "rows": [["value A", "value B"]]
    }}
  ],
  "slides": [
    {{
      "title": "slide title",
      "subtitle": "optional subtitle",
      "bullets": ["short bullet"]
    }}
  ]
}}

Use empty arrays for sheets/slides when they do not apply.

User request:
{state.message}

Internal routing hints, do not copy these words into the artifact:
- step_id: {step.id}
- artifact_metadata: {step.metadata}

Available intake/context:
{intake}

Previous backend outputs:
{_format_previous_outputs(state)}

Research summary:
{research_summary}

Sources:
{_format_sources(state)}
""".strip()


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

    if not match:
        return None

    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _extract_json_like(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        if isinstance(raw.get("title"), str) and isinstance(raw.get("body"), str):
            return raw

        for key in ("content", "document", "result", "data"):
            value = raw.get(key)
            if isinstance(value, dict) and isinstance(value.get("body"), str):
                return value

        for key in ("text", "message", "output", "response"):
            value = raw.get(key)
            if isinstance(value, str):
                parsed = _extract_json_from_text(value)
                if parsed:
                    return parsed

    if isinstance(raw, str):
        return _extract_json_from_text(raw)

    return None


def generate_office_content(step: WorkStep, state: WorkExecutionState) -> dict[str, Any]:
    """
    Generic backend document content writer.

    This avoids hardcoded document-specific templates.

    It should support:
    - leave application
    - company application
    - complaint letter
    - website report
    - memo
    - notice
    - form text
    - any other requested written document
    """

    prompt = _build_content_prompt(step, state)

    try:
        raw = call_vendor_hermes_json(prompt)

        parsed = _extract_json_like(raw)

        if parsed:
            title = _clean_text(parsed.get("title")) or _fallback_title(step, state)
            body = _clean_text(parsed.get("body")) or _fallback_body(step, state)
            artifact_format = (
                normalize_office_format(parsed.get("artifact_format"))
                or infer_office_artifact_format(
                    state.message,
                    step.metadata,
                    step.expected_artifacts,
                    step.title,
                    step.description,
                )
            )

            return {
                "title": title,
                "body": body,
                "artifact_format": artifact_format,
                "document_kind": _clean_text(parsed.get("document_kind")) or "other",
                "missing_fields": parsed.get("missing_fields")
                if isinstance(parsed.get("missing_fields"), list)
                else [],
                "sheets": parsed.get("sheets") if isinstance(parsed.get("sheets"), list) else [],
                "slides": parsed.get("slides") if isinstance(parsed.get("slides"), list) else [],
                "writer": "hermes",
            }

    except Exception as exc:
        document_kind = _infer_document_kind(step, state)
        title = _fallback_title(step, state)
        body = _fallback_body(step, state)
        artifact_format = infer_office_artifact_format(
            state.message,
            step.metadata,
            step.expected_artifacts,
            step.title,
            step.description,
        )
        topic = _topic_from_message(state.message)

        return {
            "title": title,
            "body": body,
            "artifact_format": artifact_format,
            "document_kind": document_kind,
            "missing_fields": [],
            "sheets": _fallback_sheets(title, topic) if artifact_format == "xlsx" else [],
            "slides": _fallback_slides(title, topic) if artifact_format == "pptx" else [],
            "writer": "fallback",
            "writer_error": {
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        }

    document_kind = _infer_document_kind(step, state)
    title = _fallback_title(step, state)
    body = _fallback_body(step, state)
    artifact_format = infer_office_artifact_format(
        state.message,
        step.metadata,
        step.expected_artifacts,
        step.title,
        step.description,
    )
    topic = _topic_from_message(state.message)

    return {
        "title": title,
        "body": body,
        "artifact_format": artifact_format,
        "document_kind": document_kind,
        "missing_fields": [],
        "sheets": _fallback_sheets(title, topic) if artifact_format == "xlsx" else [],
        "slides": _fallback_slides(title, topic) if artifact_format == "pptx" else [],
        "writer": "fallback",
    }
