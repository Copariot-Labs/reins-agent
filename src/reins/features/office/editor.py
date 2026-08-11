from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable

from reins.features.office.content_writer import call_reins_json, normalize_content_payload
from reins.features.office.officecli_client import OfficeCliClient, OfficeCliCommandError
from reins.features.office.schemas import (
    PRESENTATION_DESIGN_KEYS,
    PRESENTATION_FONT_CHOICES,
    OfficeDocumentRecord,
    normalize_presentation_design,
    normalize_presentation_options,
)


class OfficeRevisionError(RuntimeError):
    pass


OfficePlanner = Callable[[str, int], dict[str, Any]]

_ALLOWED_MUTATIONS = {"add", "set", "remove", "move", "swap"}
_MAX_COMMANDS = 100
_MAX_ARGUMENTS = 120
_MAX_ARGUMENT_LENGTH = 30_000
_VISUAL_REDESIGN_PATTERN = re.compile(
    r"\b(redesign|design|theme|palette|colou?r|visual|look|style|typography|font|rebrand|moderni[sz]e|unique|creative|composition|layout)\b",
    re.IGNORECASE,
)
_VISUAL_DESIGN_KEYS = tuple(
    key for key in PRESENTATION_DESIGN_KEYS if key != "palette_reason"
)


def _run_text(
    client: OfficeCliClient,
    args: list[object],
    *,
    timeout: int = 60,
    allow_failure: bool = False,
) -> str:
    try:
        result = client.run(args, timeout=timeout)
    except OfficeCliCommandError as exc:
        if allow_failure:
            return exc.stdout.strip() or exc.stderr.strip() or str(exc)
        raise
    return result.stdout.strip()


def inspect_office_document(
    record: OfficeDocumentRecord,
    *,
    client: OfficeCliClient,
) -> dict[str, str]:
    path = Path(record.path)
    if not path.exists():
        raise OfficeRevisionError(f"Office file no longer exists: {path}")

    return {
        "outline": _run_text(client, ["view", path, "outline", "--max-lines", "800"]),
        "text": _run_text(client, ["view", path, "annotated", "--max-lines", "1200"]),
        "issues": _run_text(
            client,
            ["view", path, "issues", "--limit", "100", "--json"],
            allow_failure=True,
        ),
    }


def build_revision_prompt(
    *,
    record: OfficeDocumentRecord,
    instruction: str,
    inspection: dict[str, str],
    previous_error: str = "",
) -> str:
    error_section = ""
    if previous_error:
        error_section = f"""
The previous plan was rejected or failed:
{previous_error}

Return a corrected plan. Do not repeat the invalid command.
"""

    return f"""
You are Reins, the reasoning brain for Reins Office. Plan a precise revision to
an existing {record.kind.upper()} file. Reins will execute your plan with
OfficeCLI; you do not execute shell commands yourself.

User instruction:
{instruction}

Document title: {record.title}
Document format: {record.kind}

OfficeCLI outline:
{inspection.get("outline") or "(empty)"}

OfficeCLI annotated content:
{inspection.get("text") or "(empty)"}

Current OfficeCLI issues:
{inspection.get("issues") or "(none reported)"}
{error_section}
Return only JSON with this shape:
{{
  "summary": "short description of the completed change",
  "commands": [
    {{"verb": "set", "arguments": ["/body/p[1]", "--prop", "text=Updated text"]}}
  ]
}}

Rules:
- Produce a finished, useful revision that follows the user's intent.
- Use only OfficeCLI DOM mutations: add, set, remove, move, or swap.
- Do not include the officecli binary or document file path. Reins inserts both.
- Each arguments array starts with an element path or parent path.
- For text replacement, prefer: set / --find OLD --replace NEW.
- For properties, use repeated pairs: --prop key=value.
- For Word, add paragraphs under /body with --type paragraph.
- For PowerPoint, edit shapes using paths from the outline; add shapes under a slide.
- For Excel, edit cells with paths such as /Sheet1/A1.
- Preserve content and formatting unrelated to the request.
- Never use raw XML, import, create, open, close, save, watch, or filesystem commands.
- Return an empty commands list only when the requested state is already present.
""".strip()


def build_presentation_revision_prompt(
    *,
    record: OfficeDocumentRecord,
    instruction: str,
) -> str:
    current = record.metadata.get("content")
    if not isinstance(current, dict) or not isinstance(current.get("slides"), list):
        raise OfficeRevisionError("This presentation does not have editable Reins content metadata.")

    visual_redesign = bool(_VISUAL_REDESIGN_PATTERN.search(instruction))
    design_direction = (
        """
The instruction requests a visual redesign. You MUST art-direct a visibly different result:
- Return every design field and choose a new palette and typography that suit the subject.
- Change at least the primary, accent, and background colors from the current design.
- Change the composition system and assign new variants to the slides.
- Reconsider slide layouts, hierarchy, spacing, and visual pacing while preserving factual meaning.
- Do not reuse the current theme merely because the slide content is retained.
""".strip()
        if visual_redesign
        else "Preserve the existing design unless the instruction asks for a visual change."
    )

    return f"""
You are Reins, revising an existing presentation for Reins Office.

User instruction:
{instruction}

Current presentation JSON:
{json.dumps(current, ensure_ascii=False)}

Return only the complete revised presentation JSON, with this additional top-level field:
"revision_summary": "short description of what changed"

Rules:
- Apply the user's requested change to the structured presentation content.
- Return every slide, including unchanged slides, in display order.
- Preserve the current title, slide count, notes, and unrelated content unless the instruction changes them.
- Keep the existing slide object structure and supported layouts.
- Keep visible text concise enough to fit the current design.
- The design object supports: style, composition, motif, background, surface, primary, secondary, accent, warm, text, muted, heading_font, body_font, and palette_reason.
- composition must be editorial, geometric, split, or spotlight. Every slide supports variant: auto, editorial, geometric, split, or spotlight.
- Colors must be 6-digit HEX without #. Fonts must be selected from: {", ".join(PRESENTATION_FONT_CHOICES)}.
- Do not return OfficeCLI commands, markdown, explanations, or a partial patch.
- office_format must remain "pptx".

Design direction:
{design_direction}
""".strip()


def revise_presentation_content(
    *,
    record: OfficeDocumentRecord,
    instruction: str,
    timeout: int,
    planner: OfficePlanner | None = None,
) -> dict[str, Any]:
    prompt = build_presentation_revision_prompt(record=record, instruction=instruction)
    original = record.metadata.get("content")
    original = original if isinstance(original, dict) else {}
    original_design = original.get("design") if isinstance(original.get("design"), dict) else {}
    visual_redesign = bool(_VISUAL_REDESIGN_PATTERN.search(instruction))

    def request_revision(request_prompt: str) -> dict[str, Any]:
        return planner(request_prompt, timeout) if planner else call_reins_json(request_prompt, timeout=timeout)

    def normalize_revision(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        revision_summary = str(raw.get("revision_summary") or "").strip()
        payload = raw["content"] if isinstance(raw.get("content"), dict) else raw
        returned_design = payload.get("design") if isinstance(payload.get("design"), dict) else {}
        content = normalize_content_payload(
            payload,
            office_format="pptx",
            prompt=record.prompt or instruction,
            title=record.title,
            generator="reins",
        )
        if not content.get("slides"):
            raise OfficeRevisionError("Reins returned a presentation without slides.")

        design = content.get("design") if isinstance(content.get("design"), dict) else {}
        for key in PRESENTATION_DESIGN_KEYS:
            if not returned_design.get(key) and original_design.get(key):
                design[key] = original_design[key]
        content["design"] = design
        returned_slides = payload.get("slides") if isinstance(payload.get("slides"), list) else []
        original_slides = original.get("slides") if isinstance(original.get("slides"), list) else []
        for index, slide in enumerate(content.get("slides") or []):
            returned_slide = returned_slides[index] if index < len(returned_slides) else {}
            original_slide = original_slides[index] if index < len(original_slides) else {}
            if (
                isinstance(returned_slide, dict)
                and not returned_slide.get("variant")
                and isinstance(original_slide, dict)
                and original_slide.get("variant")
            ):
                slide["variant"] = original_slide["variant"]
        content["presentation_options"] = normalize_presentation_options(
            record.metadata.get("presentation_options") or original.get("presentation_options")
        )
        content["generator"] = "reins"
        return revision_summary, content

    def design_changed(content: dict[str, Any]) -> bool:
        revised_design = content.get("design") if isinstance(content.get("design"), dict) else {}
        return any(
            str(revised_design.get(key) or "").strip().casefold()
            != str(original_design.get(key) or "").strip().casefold()
            for key in _VISUAL_DESIGN_KEYS
        )

    def structure_changed(content: dict[str, Any]) -> bool:
        original_normalized_design = normalize_presentation_design(original_design)
        revised_design = content.get("design") if isinstance(content.get("design"), dict) else {}
        if revised_design.get("composition") != original_normalized_design.get("composition"):
            return True
        original_slides = original.get("slides") if isinstance(original.get("slides"), list) else []
        revised_slides = content.get("slides") if isinstance(content.get("slides"), list) else []

        def signature(slides: list[Any], composition: str) -> tuple[tuple[str, str], ...]:
            result = []
            for slide in slides:
                item = slide if isinstance(slide, dict) else {}
                variant = str(item.get("variant") or "auto").strip().lower()
                result.append((str(item.get("layout") or "statement").strip().lower(), composition if variant == "auto" else variant))
            return tuple(result)

        return signature(revised_slides, str(revised_design.get("composition") or "structured")) != signature(
            original_slides,
            str(original_normalized_design.get("composition") or "structured"),
        )

    revision_summary, content = normalize_revision(request_revision(prompt))
    if visual_redesign and (not design_changed(content) or not structure_changed(content)):
        correction = f"""
{prompt}

Correction required: your previous result reused the current visual design. Return a genuinely
different complete design now, with new primary, accent, background, and font values.
You must also change the composition and slide variants; changing colors alone is not a redesign.
""".strip()
        revision_summary, content = normalize_revision(request_revision(correction))
        if not design_changed(content) or not structure_changed(content):
            raise OfficeRevisionError("Reins did not produce the requested visual redesign.")

    return {
        "summary": revision_summary or "Presentation updated",
        "content": content,
    }


def normalize_revision_plan(raw: dict[str, Any]) -> dict[str, Any]:
    summary = str(raw.get("summary") or "Office document updated").strip()
    commands = raw.get("commands")
    if not isinstance(commands, list):
        raise OfficeRevisionError("Reins revision plan did not contain a commands array.")
    if len(commands) > _MAX_COMMANDS:
        raise OfficeRevisionError(f"Reins revision plan exceeded {_MAX_COMMANDS} commands.")

    normalized: list[list[str]] = []
    for index, item in enumerate(commands, start=1):
        if not isinstance(item, dict):
            raise OfficeRevisionError(f"Revision command {index} must be an object.")
        verb = str(item.get("verb") or "").strip().lower()
        if verb not in _ALLOWED_MUTATIONS:
            raise OfficeRevisionError(f"Revision command {index} uses disallowed verb: {verb or '(empty)' }.")
        arguments = item.get("arguments")
        if not isinstance(arguments, list) or not arguments:
            raise OfficeRevisionError(f"Revision command {index} needs an arguments array.")
        if len(arguments) > _MAX_ARGUMENTS:
            raise OfficeRevisionError(f"Revision command {index} has too many arguments.")

        safe_arguments: list[str] = []
        for argument in arguments:
            text = str(argument)
            if "\x00" in text or len(text) > _MAX_ARGUMENT_LENGTH:
                raise OfficeRevisionError(f"Revision command {index} contains an invalid argument.")
            safe_arguments.append(text)
        if not safe_arguments[0].startswith("/"):
            raise OfficeRevisionError(f"Revision command {index} must start with a document element path.")
        normalized.append([verb, *safe_arguments])

    return {"summary": summary, "commands": normalized}


def plan_office_revision(
    prompt: str,
    timeout: int,
    *,
    planner: OfficePlanner | None = None,
) -> dict[str, Any]:
    if planner:
        return normalize_revision_plan(planner(prompt, timeout))
    return normalize_revision_plan(call_reins_json(prompt, timeout=timeout))


def apply_revision_plan(
    record: OfficeDocumentRecord,
    plan: dict[str, Any],
    *,
    client: OfficeCliClient,
) -> dict[str, Any]:
    path = Path(record.path)
    commands = plan.get("commands") or []
    client.run(["open", path], timeout=60)
    try:
        for command in commands:
            verb, *arguments = command
            client.run([verb, path, *arguments], timeout=90)
    finally:
        try:
            client.run(["close", path], timeout=60)
        except Exception:
            pass

    validation = _run_text(client, ["validate", path], timeout=90)
    issues = _run_text(
        client,
        ["view", path, "issues", "--limit", "100", "--json"],
        timeout=90,
        allow_failure=True,
    )
    return {
        "summary": str(plan.get("summary") or "Office document updated"),
        "commands": commands,
        "validation": validation,
        "issues": issues,
    }


def compact_revision_result(result: dict[str, Any]) -> dict[str, Any]:
    issues_text = str(result.get("issues") or "")
    try:
        issues: object = json.loads(issues_text) if issues_text else {}
    except json.JSONDecodeError:
        issues = issues_text
    return {
        "summary": str(result.get("summary") or "Office document updated"),
        "command_count": len(result.get("commands") or []),
        "validation": str(result.get("validation") or ""),
        "issues": issues,
    }
