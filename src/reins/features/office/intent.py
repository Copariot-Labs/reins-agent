from __future__ import annotations

from typing import Any, Callable

from reins.features.office.content_writer import call_reins_json
from reins.features.office.schemas import normalize_office_format


OfficeIntentPlanner = Callable[[str, int], dict[str, Any]]
_OFFICE_INTENTS = {"revise", "create", "chat"}
_OFFICE_FORMATS = {"docx", "xlsx", "pptx"}
_OFFICE_FORMAT_ALIASES = {
    "doc": "docx",
    "docx": "docx",
    "word": "docx",
    "xls": "xlsx",
    "xlsx": "xlsx",
    "excel": "xlsx",
    "sheet": "xlsx",
    "spreadsheet": "xlsx",
    "ppt": "pptx",
    "pptx": "pptx",
    "powerpoint": "pptx",
    "presentation": "pptx",
    "slides": "pptx",
}


def build_office_intent_prompt(
    *,
    message: str,
    document_title: str,
    document_kind: str,
) -> str:
    return f"""
You are Reins, deciding whether a user's new chat message belongs to Reins Office.

Active Office document:
- Title: {document_title}
- Format: {document_kind}

New user message:
{message}

Return only JSON:
{{
  "intent": "revise" | "create" | "chat",
  "format": "docx" | "xlsx" | "pptx" | null,
  "confidence": 0.0
}}

Decision rules:
- Choose "revise" when the user wants the active file changed in place. Understand
  indirect wording, synonyms, typos, translation requests, and references such as
  "it", "this", or "the previous file" semantically; do not depend on keywords.
- Choose "create" only when the user asks for a new or separate Office file. Set
  format to the requested Office format.
- Choose "chat" for questions, explanations, summaries to be shown only in chat,
  or requests unrelated to changing/creating an Office file.
- If the user clearly wants the active file changed but the exact change is vague,
  choose "revise". Reins Office will ask a clarification question separately.
- This is routing only. Never propose terminal commands, Python packages, plugins,
  or alternative document generators.
- Think internally and return no explanation outside the JSON object.
""".strip()


def classify_office_followup(
    *,
    message: str,
    document_title: str,
    document_kind: str,
    timeout: int = 45,
    planner: OfficeIntentPlanner | None = None,
) -> dict[str, object]:
    prompt = build_office_intent_prompt(
        message=str(message or "").strip(),
        document_title=str(document_title or "Office Document").strip(),
        document_kind=normalize_office_format(document_kind),
    )
    payload = planner(prompt, timeout) if planner else call_reins_json(prompt, timeout=timeout)
    intent = str(payload.get("intent") or "chat").strip().lower()
    if intent not in _OFFICE_INTENTS:
        intent = "chat"

    raw_format = str(payload.get("format") or "").strip().lower()
    office_format = _OFFICE_FORMAT_ALIASES.get(raw_format)
    if office_format not in _OFFICE_FORMATS:
        office_format = None
    if intent != "create":
        office_format = None

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "intent": intent,
        "format": office_format,
        "confidence": min(max(confidence, 0.0), 1.0),
    }
