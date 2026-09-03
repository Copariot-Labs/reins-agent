from __future__ import annotations

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reins.compat.bootstrap import get_project_root
from reins.features.office.schemas import (
    PRESENTATION_COMPOSITIONS,
    PRESENTATION_FONT_CHOICES,
    normalize_office_format,
    normalize_presentation_design,
    normalize_presentation_options,
    normalize_spreadsheet_design,
    normalize_title,
    normalize_word_design,
)
from reins.features.office.workflows import get_office_workflow


class OfficeContentError(RuntimeError):
    pass


class OfficeContentResponseError(OfficeContentError):
    """Raised when Reins answered, but the answer is not usable JSON."""


class OfficeContentTimeoutError(OfficeContentError):
    """Raised when Reins did not finish Office content planning in time."""


DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS = 1_200
_DEFAULT_OFFICE_MAX_OUTPUT_TOKENS = 8_000
_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|token|secret)(\s*[:=]?\s*)([^\s,;]+)"
)


def _strip_json_fence(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def _extract_json_objects(text: str) -> list[str]:
    cleaned = _strip_json_fence(text)
    objects: list[str] = []
    in_string = False
    escaped = False
    depth = 0
    start: int | None = None

    for index, char in enumerate(cleaned):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    objects.append(cleaned[start : index + 1])
                    start = None

    return objects


def _parse_json_from_text(text: str) -> dict[str, Any]:
    cleaned = _strip_json_fence(text)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    candidates = _extract_json_objects(cleaned)
    if not candidates:
        raise OfficeContentResponseError("Reins did not return a JSON object.")

    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, dict):
            return value

    raise OfficeContentResponseError("Reins returned JSON that could not be parsed.")


@dataclass(frozen=True, slots=True)
class ReinsInvocation:
    command: list[str]
    cwd: Path | None = None
    python_path: Path | None = None


def _resolve_reins_invocation() -> ReinsInvocation | None:
    # Keep the packaged runtime location available to Office diagnostics. The
    # content planner itself calls the configured model in-process and does not
    # recursively launch this command.
    service_python = os.environ.get("REINS_SERVICE_PYTHON", "").strip()
    if service_python and Path(service_python).is_file():
        return ReinsInvocation(command=[service_python, "-m", "reins.main"])

    for key in ("REINS_BIN", "HERMES_BIN"):
        value = os.environ.get(key, "").strip()
        if value:
            return ReinsInvocation(command=[value])

    found = shutil.which("reins")
    if found:
        return ReinsInvocation(command=[found])

    project_root = get_project_root()
    local_python = Path(sys.executable)
    if local_python.exists():
        return ReinsInvocation(
            command=[str(local_python), "-m", "reins.main"],
            cwd=project_root,
            python_path=project_root / "src",
        )

    return None


def _schema_instruction(
    office_format: str,
    presentation_options: dict[str, Any] | None = None,
) -> str:
    if office_format == "xlsx":
        return f"""
Return JSON:
{{
  "title": "short workbook title",
  "office_format": "xlsx",
  "body": "short workbook summary",
  "document_kind": "spreadsheet|ledger|tracker|other",
  "design": {{
    "style": "professional|financial|tracker|dashboard|minimal|colorful",
    "primary": "6-digit HEX without #",
    "secondary": "6-digit HEX without #",
    "accent": "6-digit HEX without #",
    "header_text": "6-digit HEX without #",
    "body_text": "6-digit HEX without #",
    "band_fill": "6-digit HEX without #",
    "font": "workbook-safe font",
    "header_style": "dark|accent|light|outline",
    "row_density": "compact|comfortable|spacious",
    "table_style": "medium1|medium2|medium3|medium4|light1|light2|light3|dark1|dark2|none",
    "show_title": true,
    "banded_rows": true,
    "zoom": 95,
    "design_reason": "short reason this design fits the workbook"
  }},
  "sheets": [
    {{
      "name": "Sheet name",
      "subtitle": "optional sheet purpose",
      "layout": "table|tracker|financial|dashboard|report",
      "headers": ["Column A", "Column B"],
      "rows": [["value A", "value B"]],
      "column_formats": [{{"column": "Amount", "format": "text|integer|decimal|currency|percentage|date"}}],
      "column_widths": [{{"column": "Description", "width": 28}}],
      "conditional_highlights": [{{"column": "Status", "contains": "Overdue", "fill": "FDE8E7"}}]
    }}
  ],
  "slides": [],
  "missing_fields": []
}}

Excel design rules:
- Reins is the workbook designer. Infer a suitable operational design from the data and intended use.
- If the user specifies colors, style, density, financial formatting, dashboard styling, or another design direction, follow it exactly when valid.
- Otherwise choose every design field yourself. Use 6-digit HEX colors without # and choose font from: {", ".join(PRESENTATION_FONT_CHOICES)}.
- Use at least one sheet. Rows must be arrays and all rows should align with the headers.
- Select useful number formats and column widths. Use conditional highlights only when they improve scanning or action.
- Make trackers easy to scan, financial workbooks precise, dashboards visually hierarchical, and data tables restrained.
- Never invent financial totals or formulas unsupported by the user data.
""".strip()

    if office_format == "pptx":
        options = normalize_presentation_options(presentation_options)
        return f"""
Return JSON:
{{
  "title": "short deck title",
  "office_format": "pptx",
  "body": "one-sentence deck summary",
  "document_kind": "presentation",
  "design": {{
    "style": "executive|modern|bold|minimal",
    "composition": "editorial|geometric|split|spotlight",
    "motif": "lines|blocks|circles|frames",
    "background": "6-digit HEX without #",
    "surface": "6-digit HEX without #",
    "primary": "6-digit HEX without #",
    "secondary": "6-digit HEX without #",
    "accent": "6-digit HEX without #",
    "warm": "6-digit HEX without #",
    "text": "6-digit HEX without #",
    "muted": "6-digit HEX without #",
    "heading_font": "presentation-safe font",
    "body_font": "presentation-safe font",
    "palette_reason": "short reason this visual direction fits"
  }},
  "sheets": [],
  "slides": [
    {{
      "layout": "cover|agenda|statement|kpi|cards|comparison|timeline|chart|quote|closing",
      "variant": "auto|editorial|geometric|split|spotlight",
      "eyebrow": "optional short section label",
      "title": "Slide title",
      "subtitle": "optional subtitle",
      "body": "optional short body",
      "bullets": ["short point"],
      "takeaway": "one clear audience takeaway",
      "stats": [{{"value": "18%", "label": "Growth", "detail": "short context"}}],
      "cards": [{{"title": "Card title", "body": "one short explanation", "value": "optional value"}}],
      "columns": [{{"title": "Column title", "body": "short explanation", "bullets": ["short point"]}}],
      "steps": [{{"title": "Step title", "body": "short explanation"}}],
      "chart": {{
        "type": "column|bar|line|area|pie|doughnut",
        "title": "chart title",
        "categories": ["Q1", "Q2"],
        "series": [{{"name": "Series name", "values": [10, 20]}}]
      }},
      "quote": "optional quote text",
      "attribution": "optional attribution",
      "notes": "speaker script or useful talking points"
    }}
  ],
  "missing_fields": []
}}

Presentation brief:
- Requested style: {options['style']} (when auto, choose the best listed style for the topic).
- Audience: {options['audience']}.
- Detail level: {options['detail']}.
- Create exactly {options['slide_count']} slides unless the user's prompt explicitly requires a different count.

Presentation quality rules:
- Reins is the presentation art director. Choose a distinctive visual direction for this specific topic and audience.
- Choose a composition system from: {", ".join(sorted(PRESENTATION_COMPOSITIONS - {"structured"}))}.
- Assign slide variants intentionally. Use at least three variants across the deck and avoid repeating one geometry throughout.
- Always return every design field. Use accessible, visibly differentiated colors and 6-digit HEX values without #.
- Choose heading_font and body_font from: {", ".join(PRESENTATION_FONT_CHOICES)}.
- When style is auto, make an independent design decision; do not default mechanically to the modern preset.
- Build a coherent narrative arc that can be understood from the slide titles alone.
- Start with a cover and end with a closing/next-step slide.
- Use at least four different layouts. Do not turn every slide into title plus bullets.
- Give each slide one job and one dominant visual structure.
- Use stats only for real numbers supplied by the user or defensible calculations; never invent factual metrics.
- Use charts only when meaningful numeric data exists. Categories and every series must have equal lengths.
- Keep visible copy concise: at most 5 bullets, 4 stats/cards/steps, or 2 comparison columns per slide.
- Write action-oriented, specific titles. Avoid generic titles such as "Overview" when a useful claim is possible.
- Include a useful takeaway and speaker notes on every content slide.
- Do not emit placeholders, TODOs, bracketed filler, markdown, emoji, or instructions about slide design.
- Omit unused arrays/objects or return them empty. Content must fit directly into a finished presentation.
""".strip()

    return f"""
Return JSON:
{{
  "title": "short document title",
  "office_format": "docx",
  "body": "complete Word document body",
  "document_kind": "report|letter|application|notice|memo|other",
  "design": {{
    "style": "professional|formal|editorial|modern|academic|minimal|friendly",
    "primary": "6-digit HEX without #",
    "secondary": "6-digit HEX without #",
    "accent": "6-digit HEX without #",
    "text": "6-digit HEX without #",
    "muted": "6-digit HEX without #",
    "heading_font": "document-safe font",
    "body_font": "document-safe font",
    "title_treatment": "plain|rule|band|boxed",
    "heading_treatment": "plain|rule|accent|shaded",
    "title_alignment": "left|center|right",
    "page_size": "a4|letter",
    "margins": "compact|standard|generous",
    "body_size": 11,
    "line_spacing": "1.0x|1.15x|1.3x|1.5x",
    "design_reason": "short reason this design fits the document"
  }},
  "sheets": [],
  "slides": [],
  "tables": [
    {{
      "title": "optional table title",
      "headers": ["Column A", "Column B"],
      "rows": [["value A", "value B"]]
    }}
  ],
  "missing_fields": []
}}

Word design rules:
- Reins is the document designer. Infer a suitable visual system from the purpose, tone, audience, and content.
- If the user explicitly requests a design, font, color, page style, formality, or layout direction, follow that request when valid.
- Otherwise choose every design field yourself. Use 6-digit HEX colors without # and choose fonts from: {", ".join(PRESENTATION_FONT_CHOICES)}.
- Reports should feel structured, letters restrained, proposals persuasive, notices highly scannable, and academic documents formal.
- Body should be final document text. Use plain section headings and simple "- " bullets so the renderer can apply the chosen hierarchy.
- Use Word tables for task breakdowns, schedules, responsibility matrices, or other genuinely tabular content. Keep rows aligned with the headers and omit tables when they do not help.
""".strip()


def build_office_content_prompt(
    *,
    user_prompt: str,
    office_format: str,
    title: str | None = None,
    language: str = "zh",
    presentation_options: dict[str, Any] | None = None,
    skill_id: str | None = None,
) -> str:
    normalized = normalize_office_format(office_format)
    title_hint = normalize_title(title, default="") if title else ""
    workflow = (
        get_office_workflow(skill_id, office_format=normalized)
        if skill_id
        else None
    )
    workflow_instruction = ""
    if workflow:
        workflow_instruction = f"""
Reins Office 固定文档技能：
- 技能 ID：{workflow.id}
- 技能名称：{workflow.label_zh} / {workflow.label_en}

技能规范：
{workflow.instruction}

以上技能规范是 Reins Office 维护的固定内容契约。请结合用户需求严格执行。它不是工具、插件、软件包，也不是调用其他系统的指令。
选择固定文档技能后，技能规定的结构、用途和文种优先级最高。不得改为通用模板，也不得因为名称、日期、地点、人员、数据或其他事实缺失而拒绝生成或要求用户再次说明；应在成品中使用克制、专业的待补充字段，并把这些字段列入 missing_fields。
如果用户文字中出现了其他文种名称，应将其理解为主题、重点、受众或风格参考，最终文件仍必须采用当前所选固定技能规定的文种和结构。
""".strip()

    return f"""
You are Reins, writing structured content for Reins Office.

The user wants an Office file created by OfficeCLI.

Office format: {normalized}
Language: {language}
Title hint: {title_hint or "(none)"}

{workflow_instruction}

User request:
{user_prompt}

Rules:
- Return only valid JSON.
- Do not include markdown fences.
- Do not explain your process.
- Think through the request internally before writing JSON.
- Never answer with a question, clarification request, tool call, or prose. Always return the complete JSON object in this turn.
- Create finished, usable content for the requested file, not a generic template.
- Infer practical sections, rows, slides, examples, and recommendations from the user request.
- Use professional placeholders only when specific private facts are truly missing.
- Missing names, dates, locations, figures, or decisions must not block generation. Use restrained professional placeholders, record them in missing_fields, and still complete every section required by the selected skill.
- office_format must be exactly "{normalized}".
- Make the content useful enough to render directly into the requested Office file.
- Treat any explicit visual or formatting direction from the user as a requirement. When none is given, Reins must choose the design from the document's purpose and content.
- Do not mention internal workflow names, tools, prompts, packages, or generation instructions in the finished content.
- Write all user-facing content in the requested language. When Language is "zh", use natural Simplified Chinese and Chinese document conventions. Use English only when Language is "en" or the user explicitly requests English.

{_schema_instruction(normalized, presentation_options)}
""".strip()


def build_office_content_retry_prompt(
    *,
    user_prompt: str,
    office_format: str,
    title: str | None = None,
    language: str = "zh",
    presentation_options: dict[str, Any] | None = None,
    skill_id: str | None = None,
) -> str:
    base_prompt = build_office_content_prompt(
        user_prompt=user_prompt,
        office_format=office_format,
        title=title,
        language=language,
        presentation_options=presentation_options,
        skill_id=skill_id,
    )
    return f"""
{base_prompt}

JSON response retry:
- The preceding attempt did not produce a parseable JSON object. Generate the document again from the same request and selected fixed skill.
- The selected skill already supplies the document purpose and required structure. Do not ask the user for more information and do not change to another document type.
- Your response must begin with {{ and end with }}. Return exactly one JSON object with no leading or trailing prose.
- Keep the response complete but compact enough to finish: avoid repeating paragraphs, limit Word tables to the most useful rows, and keep presentation copy concise.
""".strip()


def _office_max_output_tokens() -> int:
    try:
        configured = int(os.environ.get("REINS_OFFICE_MAX_OUTPUT_TOKENS", ""))
    except (TypeError, ValueError):
        configured = _DEFAULT_OFFICE_MAX_OUTPUT_TOKENS
    return min(12_000, max(2_000, configured))


def _response_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return ""
    first = choices[0]
    message = getattr(first, "message", None)
    if message is None and isinstance(first, dict):
        message = first.get("message")
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _call_office_content_model(
    messages: list[dict[str, str]],
    *,
    timeout: int,
) -> Any:
    # The Office worker already runs inside the bootstrapped Reins runtime.
    # Calling the configured model here avoids starting a second full agent
    # process, which is especially expensive in the packaged Windows build.
    from agent.auxiliary_client import call_llm

    return call_llm(
        task="office_content",
        messages=messages,
        temperature=0,
        max_tokens=_office_max_output_tokens(),
        timeout=float(timeout),
    )


def _is_timeout_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    detail = str(exc).lower()
    return "timeout" in name or "timed out" in detail or "time out" in detail


def _safe_content_error(exc: Exception) -> str:
    detail = str(exc or "").strip()
    if not detail:
        return type(exc).__name__
    if "Command '[" in detail or "Command \"[" in detail:
        return "The Reins content planning process did not complete."
    detail = _SECRET_RE.sub(r"\1\2[redacted]", detail)
    detail = re.sub(r"\s+", " ", detail).strip()
    return detail[:700]


def _call_reins_json(prompt: str, *, timeout: int) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Reins Office content planner. Follow the selected fixed skill, "
                "produce complete usable content, and return exactly one JSON object with no markdown."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        response = _call_office_content_model(messages, timeout=timeout)
    except Exception as exc:
        if _is_timeout_error(exc):
            raise OfficeContentTimeoutError(
                f"Reins content planning timed out after {timeout} seconds."
            ) from exc
        raise OfficeContentError(_safe_content_error(exc)) from exc

    content = _response_content(response)
    if not content:
        raise OfficeContentResponseError("Reins returned an empty Office content response.")
    return _parse_json_from_text(content)


def call_reins_json(
    prompt: str,
    *,
    timeout: int = DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call the configured Reins model and require a JSON object response."""
    return _call_reins_json(prompt, timeout=timeout)


def reins_status() -> dict[str, object]:
    invocation = _resolve_reins_invocation()
    return {
        "available": invocation is not None,
        "command": invocation.command if invocation else None,
    }


def _topic_from_prompt(prompt: str) -> str:
    text = re.sub(r"\s+", " ", str(prompt or "")).strip(" .")
    text = re.sub(
        r"^(please|can you|could you|create|make|generate|write|prepare|draft|build|produce)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .")
    text = re.sub(
        r"^(a|an|the)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" .")
    return text[:90] or "Requested Office Document"


def _fallback_docx(prompt: str, title: str) -> dict[str, Any]:
    topic = _topic_from_prompt(prompt)
    body = "\n\n".join(
        [
            "Overview",
            f"This document has been prepared for {topic}.",
            "Key Points",
            "- Confirm dates, names, amounts, and responsible parties.",
            "- Review the content with the relevant stakeholder.",
            "- Save the approved version with the project record.",
            "Details",
            "[Add final details here.]",
        ]
    )
    return {
        "title": title,
        "office_format": "docx",
        "body": body,
        "document_kind": "other",
        "sheets": [],
        "slides": [],
        "missing_fields": [],
        "generator": "fallback",
    }


def _fallback_xlsx(prompt: str, title: str) -> dict[str, Any]:
    topic = _topic_from_prompt(prompt)
    return {
        "title": title,
        "office_format": "xlsx",
        "body": f"Workbook for {topic}.",
        "document_kind": "spreadsheet",
        "sheets": [
            {
                "name": "Tracking",
                "headers": ["Item", "Description", "Owner", "Due Date", "Status"],
                "rows": [
                    [1, f"Confirm scope for {topic}", "[Name]", "[Date]", "Pending"],
                    [2, "Collect supporting information", "[Name]", "[Date]", "Pending"],
                    [3, "Review and finalize", "[Name]", "[Date]", "Pending"],
                ],
            }
        ],
        "slides": [],
        "missing_fields": [],
        "generator": "fallback",
    }


def _fallback_pptx(
    prompt: str,
    title: str,
    presentation_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    topic = _topic_from_prompt(prompt)
    options = normalize_presentation_options(presentation_options)
    return {
        "title": title,
        "office_format": "pptx",
        "body": f"Presentation for {topic}.",
        "document_kind": "presentation",
        "design": {
            "style": "modern" if options["style"] == "auto" else options["style"],
            "palette_reason": "Clear, contemporary presentation styling.",
        },
        "sheets": [],
        "slides": [
            {
                "layout": "cover",
                "title": title,
                "subtitle": f"A practical briefing on {topic}",
                "takeaway": "Prepared by Reins Office",
                "notes": f"Introduce the purpose of this briefing on {topic}.",
            },
            {
                "layout": "cards",
                "title": "The briefing aligns context, decisions, and action",
                "cards": [
                    {"title": "Context", "body": f"Clarify what matters most for {topic}."},
                    {"title": "Decisions", "body": "Surface the choices that need stakeholder input."},
                    {"title": "Action", "body": "Translate the discussion into owned next steps."},
                ],
                "takeaway": "A shared frame keeps the discussion focused.",
                "notes": "Walk through the three outcomes expected from the session.",
            },
            {
                "layout": "comparison",
                "title": "Current understanding and open decisions need separation",
                "columns": [
                    {
                        "title": "What we know",
                        "bullets": [f"The work centers on {topic}.", "Stakeholder alignment is required."],
                    },
                    {
                        "title": "What to decide",
                        "bullets": ["Confirm scope and success criteria.", "Assign accountable owners."],
                    },
                ],
                "takeaway": "Resolve decisions without reopening settled context.",
                "notes": "Confirm known facts first, then focus discussion on the open choices.",
            },
            {
                "layout": "timeline",
                "title": "A short execution path turns alignment into progress",
                "steps": [
                    {"title": "Confirm", "body": "Validate scope and assumptions."},
                    {"title": "Assign", "body": "Name owners and target dates."},
                    {"title": "Deliver", "body": "Complete the agreed work."},
                    {"title": "Review", "body": "Measure results and adjust."},
                ],
                "takeaway": "Every next step needs an owner and a review point.",
                "notes": "Use this sequence to agree the immediate operating cadence.",
            },
            {
                "layout": "closing",
                "title": "Move forward with a clear owner and first milestone",
                "bullets": [
                    "Confirm the accountable owner.",
                    "Set the first measurable milestone.",
                    "Schedule the next review.",
                ],
                "takeaway": "Turn this briefing into one concrete commitment.",
                "notes": "Close by confirming the owner, first milestone, and review date.",
            },
        ],
        "missing_fields": [],
        "generator": "fallback",
    }


def _fallback_content(
    prompt: str,
    office_format: str,
    title: str | None,
    presentation_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    topic = _topic_from_prompt(prompt)
    fallback_title = normalize_title(title or topic)
    normalized = normalize_office_format(office_format)
    if normalized == "xlsx":
        return _fallback_xlsx(prompt, fallback_title)
    if normalized == "pptx":
        return _fallback_pptx(prompt, fallback_title, presentation_options)
    return _fallback_docx(prompt, fallback_title)


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _fixed_skill_payload_needs_retry(
    raw: dict[str, Any],
    *,
    office_format: str,
) -> bool:
    normalized = normalize_office_format(office_format)
    if normalized == "xlsx":
        has_content = bool(_list_or_empty(raw.get("sheets")))
    elif normalized == "pptx":
        has_content = bool(_list_or_empty(raw.get("slides")))
    else:
        has_content = bool(
            str(raw.get("body") or "").strip()
            or _list_or_empty(raw.get("tables"))
        )
    if not has_content:
        return True

    structured_content = any(
        _list_or_empty(raw.get(key))
        for key in ("tables", "sheets", "slides")
    )
    response_text = " ".join(
        str(raw.get(key) or "").strip()
        for key in ("title", "body")
    )
    if structured_content or len(response_text) > 500:
        return False
    return bool(
        re.search(
            r"(?:请|需要).{0,12}(?:提供|补充|告诉我).{0,24}(?:信息|详情|内容|要求)"
            r"|\b(?:please\s+(?:provide|share|describe)|need\s+more\s+(?:information|details))\b",
            response_text,
            flags=re.IGNORECASE,
        )
    )


def normalize_content_payload(
    raw: dict[str, Any],
    *,
    office_format: str,
    prompt: str,
    title: str | None = None,
    generator: str = "reins",
) -> dict[str, Any]:
    normalized = normalize_office_format(raw.get("office_format") or office_format)
    if normalized != normalize_office_format(office_format):
        normalized = normalize_office_format(office_format)

    safe_title = normalize_title(raw.get("title") or title or _topic_from_prompt(prompt))

    sheets: list[dict[str, Any]] = []
    for sheet in _list_or_empty(raw.get("sheets")):
        if not isinstance(sheet, dict):
            continue
        headers = sheet.get("headers") or sheet.get("columns") or []
        rows = sheet.get("rows") or []
        sheets.append(
            {
                "name": str(sheet.get("name") or "Sheet1"),
                "subtitle": str(sheet.get("subtitle") or ""),
                "layout": str(sheet.get("layout") or "table").strip().lower(),
                "headers": headers if isinstance(headers, list) else [],
                "rows": rows if isinstance(rows, list) else [],
                "column_formats": _list_or_empty(sheet.get("column_formats"))[:50],
                "column_widths": _list_or_empty(sheet.get("column_widths"))[:50],
                "conditional_highlights": _list_or_empty(sheet.get("conditional_highlights"))[:25],
            }
        )

    slides: list[dict[str, Any]] = []
    for slide in _list_or_empty(raw.get("slides")):
        if not isinstance(slide, dict):
            continue
        bullets = slide.get("bullets") or []
        chart = slide.get("chart") if isinstance(slide.get("chart"), dict) else {}
        slides.append(
            {
                "layout": str(slide.get("layout") or "statement").strip().lower(),
                "variant": (
                    str(slide.get("variant") or "auto").strip().lower()
                    if str(slide.get("variant") or "auto").strip().lower()
                    in {"auto", *PRESENTATION_COMPOSITIONS}
                    else "auto"
                ),
                "eyebrow": str(slide.get("eyebrow") or ""),
                "title": str(slide.get("title") or safe_title),
                "subtitle": str(slide.get("subtitle") or ""),
                "body": str(slide.get("body") or ""),
                "bullets": bullets if isinstance(bullets, list) else [],
                "takeaway": str(slide.get("takeaway") or ""),
                "stats": _list_or_empty(slide.get("stats"))[:4],
                "cards": _list_or_empty(slide.get("cards"))[:4],
                "columns": _list_or_empty(slide.get("columns"))[:2],
                "steps": _list_or_empty(slide.get("steps"))[:4],
                "chart": chart,
                "quote": str(slide.get("quote") or ""),
                "attribution": str(slide.get("attribution") or ""),
                "notes": str(slide.get("notes") or ""),
            }
        )

    tables: list[dict[str, Any]] = []
    for table in _list_or_empty(raw.get("tables")):
        if not isinstance(table, dict):
            continue
        headers = table.get("headers") or table.get("columns") or []
        rows = table.get("rows") or []
        tables.append(
            {
                "title": str(table.get("title") or ""),
                "headers": headers if isinstance(headers, list) else [],
                "rows": rows if isinstance(rows, list) else [],
            }
        )

    if normalized == "pptx":
        design = normalize_presentation_design(raw.get("design"))
    elif normalized == "xlsx":
        design = normalize_spreadsheet_design(raw.get("design"))
    else:
        design = normalize_word_design(raw.get("design"))

    return {
        "title": safe_title,
        "office_format": normalized,
        "body": str(raw.get("body") or ""),
        "document_kind": str(raw.get("document_kind") or "other"),
        "missing_fields": _list_or_empty(raw.get("missing_fields")),
        "sheets": sheets,
        "slides": slides,
        "tables": tables,
        "design": design,
        "generator": str(raw.get("generator") or generator),
    }


def _apply_presentation_options(
    content: dict[str, Any],
    *,
    office_format: str,
    presentation_options: dict[str, Any] | None,
) -> dict[str, Any]:
    if normalize_office_format(office_format) != "pptx":
        return content

    options = normalize_presentation_options(presentation_options)
    design = content.get("design") if isinstance(content.get("design"), dict) else {}
    generated_style = normalize_presentation_options({"style": design.get("style")})["style"]
    design = dict(design)
    design["style"] = (
        options["style"]
        if options["style"] != "auto"
        else ("modern" if generated_style == "auto" else generated_style)
    )
    content["design"] = design
    content["presentation_options"] = options
    return content


def generate_office_content(
    *,
    prompt: str,
    office_format: str,
    title: str | None = None,
    language: str = "zh",
    timeout: int = DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    use_reins: bool = True,
    presentation_options: dict[str, Any] | None = None,
    skill_id: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_office_format(office_format)
    if skill_id:
        get_office_workflow(skill_id, office_format=normalized)

    brain_disabled = (
        os.environ.get("REINS_OFFICE_DISABLE_BRAIN") == "1"
        or os.environ.get("REINS_OFFICE_DISABLE_HERMES") == "1"
    )
    if use_reins and not brain_disabled:
        try:
            content_prompt = build_office_content_prompt(
                user_prompt=prompt,
                office_format=normalized,
                title=title,
                language=language,
                presentation_options=presentation_options,
                skill_id=skill_id,
            )
            try:
                raw = _call_reins_json(content_prompt, timeout=timeout)
            except OfficeContentResponseError:
                if not skill_id:
                    raise
                raw = _call_reins_json(
                    build_office_content_retry_prompt(
                        user_prompt=prompt,
                        office_format=normalized,
                        title=title,
                        language=language,
                        presentation_options=presentation_options,
                        skill_id=skill_id,
                    ),
                    timeout=timeout,
                )
            else:
                if skill_id and _fixed_skill_payload_needs_retry(
                    raw,
                    office_format=normalized,
                ):
                    raw = _call_reins_json(
                        build_office_content_retry_prompt(
                            user_prompt=prompt,
                            office_format=normalized,
                            title=title,
                            language=language,
                            presentation_options=presentation_options,
                            skill_id=skill_id,
                        ),
                        timeout=timeout,
                    )
            return _apply_presentation_options(
                normalize_content_payload(
                    raw,
                    office_format=normalized,
                    prompt=prompt,
                    title=title,
                    generator="reins",
                ),
                office_format=normalized,
                presentation_options=presentation_options,
            )
        except Exception as exc:
            if os.environ.get("REINS_OFFICE_ALLOW_FALLBACK") == "1":
                fallback = _fallback_content(prompt, normalized, title, presentation_options)
                fallback["generator"] = "fallback"
                fallback["generator_error"] = {
                    "error_type": type(exc).__name__,
                    "error": _safe_content_error(exc),
                }
                return _apply_presentation_options(
                    normalize_content_payload(
                        fallback,
                        office_format=normalized,
                        prompt=prompt,
                        title=title,
                        generator="fallback",
                    ),
                    office_format=normalized,
                    presentation_options=presentation_options,
                )
            if isinstance(exc, OfficeContentError):
                raise
            raise OfficeContentError(
                "Reins failed to generate Office content. "
                f"{type(exc).__name__}: {_safe_content_error(exc)}"
            ) from exc

    return _apply_presentation_options(
        normalize_content_payload(
            _fallback_content(prompt, normalized, title, presentation_options),
            office_format=normalized,
            prompt=prompt,
            title=title,
            generator="fallback",
        ),
        office_format=normalized,
        presentation_options=presentation_options,
    )
