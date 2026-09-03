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
_WORD_PARAGRAPH_PATH_PATTERN = re.compile(
    r"(?P<base>(?P<parent>/(?:[^/\s\[\]\"']+(?:\[[^\]\s]+\])?/)*)"
    r"p(?:\[@paraId=(?P<para_id>[0-9A-Fa-f]+)\]|\[(?P<position>\d+)\]))"
)
_PRESENTATION_ELEMENT_PATH_PATTERN = re.compile(
    r"(?P<base>(?P<parent>/(?:[^/\s\[\]\"']+(?:\[[^\]\s]+\])?/)*)"
    r"(?P<kind>shape|picture|table|chart|group|connector)"
    r"(?:\[@id=(?P<element_id>\d+)\]|\[(?P<position>\d+)\]))",
    re.IGNORECASE,
)
_UNSUPPORTED_PRESENTATION_SELECTOR_PATTERN = re.compile(
    r"/(?:shape|picture|table|chart|group|connector|placeholder)\[@",
    re.IGNORECASE,
)
_EXCEL_SHEET_HEADER_PATTERN = re.compile(r"^=== Sheet: (?P<name>.+?) ===$")
_EXCEL_CELL_LINE_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<cell>[A-Za-z]{1,3}\d+)(?P<content>:.*)$"
)
_WORD_FORMATTING_FIELDS = (
    "styleId,styleName,font,size,color,bold,italic,align,spaceBefore,spaceAfter,"
    "lineSpacing,firstLineIndent,listStyle,numId,numLevel"
)
_WORD_INHERITED_FORMAT_KEYS = (
    "style",
    "font",
    "size",
    "color",
    "bold",
    "italic",
    "align",
    "spaceBefore",
    "spaceAfter",
    "lineSpacing",
    "firstLineIndent",
)
_NATURAL_CHARACTER_SPACING_PATTERN = re.compile(
    r"^\s*(?P<value>[+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*"
    r"(?:characters?|chars?|character\s*widths?|字符|个字符|字)\s*$",
    re.IGNORECASE,
)


def _normalize_revision_property(argument: str) -> str:
    name, separator, value = argument.partition("=")
    if not separator:
        return argument
    if name.strip().casefold() not in {"spacing", "charspacing", "letterspacing"}:
        return argument
    natural_spacing = _NATURAL_CHARACTER_SPACING_PATTERN.fullmatch(value)
    if not natural_spacing:
        return argument
    number = float(natural_spacing.group("value"))
    if not (-1000 <= number <= 1000):
        return argument
    normalized_number = f"{number:g}"
    return f"{name}={normalized_number}pt"


def _run_text(
    client: OfficeCliClient,
    args: list[object],
    *,
    timeout: int = 60,
    allow_failure: bool = False,
) -> str:
    try:
        result = client.run(
            args,
            timeout=timeout,
            env_overrides={"OFFICECLI_NO_AUTO_RESIDENT": "1"},
        )
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

    inspection = {
        "outline": _run_text(client, ["view", path, "outline", "--max-lines", "800"]),
        "text": _run_text(client, ["view", path, "annotated", "--max-lines", "1200"]),
        "issues": _run_text(
            client,
            ["view", path, "issues", "--limit", "100", "--json"],
            allow_failure=True,
        ),
    }
    if record.kind == "docx":
        inspection["formatting"] = _run_text(
            client,
            [
                "query",
                path,
                "paragraph",
                "--compact",
                "--fields",
                _WORD_FORMATTING_FIELDS,
            ],
            timeout=90,
            allow_failure=True,
        )
    elif record.kind == "pptx":
        elements = _run_text(
            client,
            [
                "query",
                path,
                "*",
                "--compact",
                "--fields",
                "x,y,width,height",
            ],
            timeout=90,
            allow_failure=True,
        )
        if not re.search(r"/slide\[\d+\]/", elements):
            elements = _run_text(
                client,
                ["query", path, "shape", "--json"],
                timeout=90,
                allow_failure=True,
            )
        inspection["elements"] = elements
    return inspection


def _replace_path_aliases(value: str, aliases: dict[str, str]) -> str:
    rewritten = value
    for source, target in sorted(
        aliases.items(), key=lambda item: len(item[0]), reverse=True
    ):
        rewritten = re.sub(
            rf"{re.escape(source)}(?=/|$|[\s\],;\"'])",
            lambda _match, replacement=target: replacement,
            rewritten,
            flags=re.IGNORECASE,
        )
    return rewritten


def canonicalize_word_revision_inspection(
    inspection: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Replace Word stable paragraph IDs with positional paths for CLI compatibility."""
    aliases: dict[str, str] = {}
    seen_by_parent: dict[str, set[str]] = {}
    next_position_by_parent: dict[str, int] = {}

    # Annotated output contains paragraphs in document order. Outline is kept as
    # a fallback for OfficeCLI versions that expose more paths there.
    for field in ("text", "outline"):
        for match in _WORD_PARAGRAPH_PATH_PATTERN.finditer(inspection.get(field) or ""):
            base = match.group("base")
            parent = match.group("parent")
            seen = seen_by_parent.setdefault(parent, set())
            identity = base.casefold()
            if identity in seen:
                continue
            seen.add(identity)

            explicit_position = match.group("position")
            if explicit_position:
                next_position_by_parent[parent] = max(
                    next_position_by_parent.get(parent, 0),
                    int(explicit_position),
                )
                continue

            position = next_position_by_parent.get(parent, 0) + 1
            next_position_by_parent[parent] = position
            aliases[base] = f"{parent}p[{position}]"

    if not aliases:
        return dict(inspection), {}

    alias_lookup = {source.casefold(): target for source, target in aliases.items()}

    def replace_path(match: re.Match[str]) -> str:
        return alias_lookup.get(match.group("base").casefold(), match.group("base"))

    canonical = {
        key: _WORD_PARAGRAPH_PATH_PATTERN.sub(replace_path, value)
        for key, value in inspection.items()
    }
    return canonical, aliases


def _word_formatting_rows(formatting: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in formatting.splitlines():
        columns = line.split("\t")
        if not columns or not columns[0].startswith("/"):
            continue
        row = {"path": columns[0]}
        for column in columns[3:]:
            key, separator, value = column.partition("=")
            if separator:
                row[key.strip()] = value.strip()
        rows.append(row)
    return rows


def inherit_word_revision_formatting(
    plan: dict[str, Any],
    inspection: dict[str, str],
) -> dict[str, Any]:
    """Fill missing paragraph formatting from the document's own best exemplar."""
    rows = _word_formatting_rows(inspection.get("formatting") or "")
    if not rows:
        return plan
    rows_by_path = {row["path"].casefold(): row for row in rows}

    def value_for(row: dict[str, str], key: str) -> str:
        if key == "style":
            return row.get("styleId") or ""
        return row.get(key) or ""

    def row_score(row: dict[str, str]) -> int:
        return sum(bool(value_for(row, key)) for key in _WORD_INHERITED_FORMAT_KEYS)

    def exemplar_for(properties: dict[str, str]) -> dict[str, str] | None:
        requested_style = properties.get("style", "").casefold()
        requested_list = properties.get("liststyle", "").casefold()
        candidates = rows
        if requested_style:
            if requested_style == "normal":
                candidates = [
                    row
                    for row in rows
                    if (row.get("styleId") or "").casefold() in {"", "normal"}
                ]
            else:
                candidates = [
                    row
                    for row in rows
                    if requested_style
                    in {
                        (row.get("styleId") or "").casefold(),
                        (row.get("styleName") or "").casefold(),
                    }
                ]
        elif requested_list:
            candidates = [
                row
                for row in rows
                if (row.get("listStyle") or "").casefold() == requested_list
            ]
        else:
            candidates = [
                row
                for row in rows
                if not (row.get("listStyle") or "").strip()
                and (row.get("styleId") or "").casefold() in {"", "normal"}
            ]
        return max(candidates, key=row_score, default=None)

    commands: list[list[str]] = []
    for command in plan.get("commands") or []:
        rewritten = list(command)
        is_paragraph_add = (
            len(rewritten) >= 4
            and rewritten[0] == "add"
            and rewritten[1].casefold() == "/body"
            and "--type" in rewritten
        )
        if is_paragraph_add:
            type_index = rewritten.index("--type")
            element_type = (
                rewritten[type_index + 1].casefold()
                if type_index + 1 < len(rewritten)
                else ""
            )
            is_paragraph_add = element_type in {"paragraph", "p"}

        target_row = (
            rows_by_path.get(rewritten[1].casefold())
            if len(rewritten) >= 2 and rewritten[0] == "set"
            else None
        )
        if not is_paragraph_add and target_row is None:
            commands.append(rewritten)
            continue

        properties: dict[str, str] = {}
        for index, argument in enumerate(rewritten[:-1]):
            if argument != "--prop":
                continue
            key, separator, value = rewritten[index + 1].partition("=")
            if separator:
                normalized_key = key.strip().casefold()
                if normalized_key in {"styleid", "stylename"}:
                    normalized_key = "style"
                properties[normalized_key] = value

        selection_properties = dict(properties)
        if target_row is not None:
            if "style" not in selection_properties and target_row.get("styleId"):
                selection_properties["style"] = target_row["styleId"]
            if "liststyle" not in selection_properties and target_row.get("listStyle"):
                selection_properties["liststyle"] = target_row["listStyle"]

        exemplar = exemplar_for(selection_properties)
        if exemplar is None:
            commands.append(rewritten)
            continue

        for key in _WORD_INHERITED_FORMAT_KEYS:
            if key.casefold() in properties:
                continue
            if target_row is not None and value_for(target_row, key):
                continue
            value = value_for(exemplar, key)
            if value:
                rewritten.extend(["--prop", f"{key}={value}"])
        commands.append(rewritten)

    return {**plan, "commands": commands}


def canonicalize_excel_revision_inspection(
    inspection: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Expose complete editable cell paths, including Chinese worksheet names."""
    sheet_names: list[str] = []
    current_sheet = ""
    annotated_lines: list[str] = []
    for line in (inspection.get("text") or "").splitlines():
        sheet_match = _EXCEL_SHEET_HEADER_PATTERN.match(line.strip())
        if sheet_match:
            current_sheet = sheet_match.group("name").strip()
            if current_sheet and current_sheet not in sheet_names:
                sheet_names.append(current_sheet)
            annotated_lines.append(line)
            if current_sheet:
                annotated_lines.append(f"Editable worksheet path: /{current_sheet}")
            continue

        cell_match = _EXCEL_CELL_LINE_PATTERN.match(line)
        if current_sheet and cell_match:
            cell = cell_match.group("cell").upper()
            annotated_lines.append(
                f"{cell_match.group('indent')}[/{current_sheet}/{cell}] "
                f"{cell}{cell_match.group('content')}"
            )
            continue
        annotated_lines.append(line)

    aliases: dict[str, str] = {}
    real_sheet_names = {name.casefold() for name in sheet_names}
    for index, sheet_name in enumerate(sheet_names, start=1):
        target = f"/{sheet_name}"
        aliases[f"/sheet[{index}]"] = target
        for placeholder in (f"/Sheet{index}", f"/工作表{index}"):
            if placeholder[1:].casefold() not in real_sheet_names:
                aliases[placeholder] = target

    canonical = dict(inspection)
    canonical["text"] = "\n".join(annotated_lines)
    return canonical, aliases


def canonicalize_presentation_revision_inspection(
    inspection: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Convert stable PowerPoint element IDs into Windows-compatible positions."""
    aliases: dict[str, str] = {}
    seen_by_parent_and_kind: dict[tuple[str, str], set[str]] = {}
    next_position: dict[tuple[str, str], int] = {}

    for field in ("elements", "text", "outline"):
        for match in _PRESENTATION_ELEMENT_PATH_PATTERN.finditer(
            inspection.get(field) or ""
        ):
            base = match.group("base")
            parent = match.group("parent")
            kind = match.group("kind").lower()
            key = (parent.casefold(), kind)
            seen = seen_by_parent_and_kind.setdefault(key, set())
            identity = base.casefold()
            if identity in seen:
                continue
            seen.add(identity)

            explicit_position = match.group("position")
            if explicit_position:
                next_position[key] = max(
                    next_position.get(key, 0),
                    int(explicit_position),
                )
                continue

            position = next_position.get(key, 0) + 1
            next_position[key] = position
            aliases[base] = f"{parent}{kind}[{position}]"

    canonical = {
        key: _replace_path_aliases(value, aliases)
        for key, value in inspection.items()
    }
    return canonical, aliases


def canonicalize_revision_plan_paths(
    plan: dict[str, Any],
    aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Translate format-specific aliases before invoking OfficeCLI."""
    alias_lookup = {
        source.casefold(): target for source, target in (aliases or {}).items()
    }

    def replace_path(match: re.Match[str]) -> str:
        return alias_lookup.get(match.group("base").casefold(), match.group("base"))

    commands: list[list[str]] = []
    for command in plan.get("commands") or []:
        rewritten = list(command)
        for index in range(1, len(rewritten)):
            rewritten[index] = _replace_path_aliases(rewritten[index], aliases or {})
            rewritten[index] = _WORD_PARAGRAPH_PATH_PATTERN.sub(
                replace_path, rewritten[index]
            )
            if "@paraId=" in rewritten[index]:
                raise OfficeRevisionError(
                    "The revision used a Word paragraph ID that this OfficeCLI build cannot edit. "
                    "Use a positional paragraph path from the inspected document instead."
                )
            if _UNSUPPORTED_PRESENTATION_SELECTOR_PATTERN.search(rewritten[index]):
                raise OfficeRevisionError(
                    "The revision used a PowerPoint attribute selector that this OfficeCLI build "
                    "cannot edit. Use a positional element path from the inspected presentation instead."
                )
        commands.append(rewritten)

    return {
        **plan,
        "commands": commands,
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

    last_revision = record.metadata.get("last_revision")
    revision_context = "(this is the first recorded revision)"
    if isinstance(last_revision, dict):
        revision_context = json.dumps(
            {
                "instruction": last_revision.get("instruction"),
                "summary": last_revision.get("summary"),
                "changed_paths": last_revision.get("changed_paths") or [],
            },
            ensure_ascii=False,
        )

    return f"""
You are Reins, the reasoning brain for Reins Office. Plan a precise revision to
an existing {record.kind.upper()} file. Reins will execute your plan with
OfficeCLI; you do not execute shell commands yourself.

User instruction:
{instruction}

Document title: {record.title}
Document format: {record.kind}

Most recent successful revision:
{revision_context}

OfficeCLI outline:
{inspection.get("outline") or "(empty)"}

OfficeCLI annotated content:
{inspection.get("text") or "(empty)"}

OfficeCLI editable elements:
{inspection.get("elements") or "(use the exact paths shown in the annotated content)"}

OfficeCLI Word paragraph formatting:
{inspection.get("formatting") or "(not a Word document or no paragraph formatting was returned)"}

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
- Preserve the existing document language. Use Chinese by default only when the existing language is Chinese or unclear, unless the user explicitly requests another language.
- For Word, use the positional paragraph paths shown above, such as /body/p[1].
- Never use Word @paraId selectors; the packaged OfficeCLI requires positional paths for revisions.
- For Word and PowerPoint text replacement, prefer: set / --find OLD --replace NEW.
- For properties, use repeated pairs: --prop key=value.
- For Word character spacing properties (spacing, charSpacing, or letterSpacing), use a finite number with an OfficeCLI unit such as 2pt. Never use natural-language values such as "2 characters" or "两个字符".
- For Word, add paragraphs under /body with --type paragraph.
- Treat the existing file as the design source of truth. For Word design or formatting changes, copy the exact supported property values shown under "Word paragraph formatting" from an analogous existing title, heading, body paragraph, or list item.
- A Word style name alone may not reproduce the visible design because existing paragraphs can also use direct size, color, bold, spacing, and alignment properties. Apply those shown properties when matching the design.
- When adding Word paragraphs, include the analogous paragraph's supported formatting properties in the add command. Do not combine --from with --prop; OfficeCLI rejects that combination.
- For PowerPoint, use the exact positional paths under "editable elements"; never use @id, @name, or @type selectors.
- For PowerPoint text, set the target shape with --prop text=NEW; add shapes only under a slide path.
- For Excel, use the exact worksheet and cell paths shown above, including Chinese worksheet names.
- For Excel values use --prop value=NEW, and for formulas use --prop formula=FORMULA; never use text as a cell property.
- For Excel, never use --find/--replace and never put find or replace inside --prop.
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
        for argument_index, argument in enumerate(safe_arguments[:-1]):
            if argument == "--prop":
                safe_arguments[argument_index + 1] = _normalize_revision_property(
                    safe_arguments[argument_index + 1]
                )
        if not safe_arguments[0].startswith("/"):
            raise OfficeRevisionError(f"Revision command {index} must start with a document element path.")
        for argument_index, argument in enumerate(safe_arguments[:-1]):
            if argument != "--prop":
                continue
            property_name = safe_arguments[argument_index + 1].split("=", 1)[0].strip().lower()
            if property_name in {"find", "replace"}:
                raise OfficeRevisionError(
                    f"Revision command {index} uses {property_name} as a property; "
                    "use the supported mutation flags or set the cell value directly."
                )
        if verb == "add" and "--from" in safe_arguments and "--prop" in safe_arguments:
            raise OfficeRevisionError(
                f"Revision command {index} combines --from with --prop. "
                "Use a typed add with explicit properties, or clone first and set the copy separately."
            )
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
    plan = canonicalize_revision_plan_paths(plan)
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

    try:
        validation = _run_text(client, ["validate", path], timeout=90)
        issues = _run_text(
            client,
            ["view", path, "issues", "--limit", "100", "--json"],
            timeout=90,
            allow_failure=True,
        )
    finally:
        try:
            client.run(["close", path], timeout=60)
        except Exception:
            pass
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
    changed_paths = []
    for command in result.get("commands") or []:
        if len(command) >= 2 and command[1] not in changed_paths:
            changed_paths.append(command[1])
        if len(changed_paths) >= 30:
            break
    return {
        "summary": str(result.get("summary") or "Office document updated"),
        "command_count": len(result.get("commands") or []),
        "changed_paths": changed_paths,
        "validation": str(result.get("validation") or ""),
        "issues": issues,
    }
