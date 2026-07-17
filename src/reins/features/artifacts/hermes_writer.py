from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from reins.features.artifacts.schema import normalize_artifact_format


class HermesArtifactError(Exception):
    pass


def _strip_markdown_json_fence(value: str) -> str:
    text = str(value or "").strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    return text


def _extract_json_candidates(text: str) -> list[str]:
    cleaned = _strip_markdown_json_fence(text)

    candidates: list[str] = []

    in_string = False
    escaped = False
    depth = 0
    start_index: int | None = None

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
                start_index = index
            depth += 1
            continue

        if char == "}":
            if depth > 0:
                depth -= 1

                if depth == 0 and start_index is not None:
                    candidates.append(cleaned[start_index : index + 1])
                    start_index = None

    return candidates


def _extract_best_json_object(text: str) -> str:
    cleaned = _strip_markdown_json_fence(text)

    if not cleaned:
        raise HermesArtifactError("Model returned empty output.")

    candidates = _extract_json_candidates(cleaned)

    if not candidates:
        raise HermesArtifactError(
            "Could not find a balanced JSON object in model output.\n\n"
            f"Output preview:\n{cleaned[:3000]}"
        )

    artifact_candidates: list[str] = []

    for candidate in candidates:
        if '"title"' in candidate and (
            '"body"' in candidate
            or '"slides"' in candidate
            or '"sheets"' in candidate
        ):
            artifact_candidates.append(candidate)

    if artifact_candidates:
        return artifact_candidates[-1]

    return max(candidates, key=len)


def _repair_json_string_chars(value: str) -> str:
    """
    Repair common local-model JSON issues inside quoted strings.

    Repairs:
    - Raw newlines/control chars inside strings.
    - Invalid escapes like \\[ or \\*.
    - Keeps valid JSON escapes.
    """
    result: list[str] = []
    in_string = False
    escaped = False

    valid_simple_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t"}

    index = 0
    length = len(value)

    while index < length:
        char = value[index]

        if escaped:
            if char in valid_simple_escapes:
                result.append("\\")
                result.append(char)
                escaped = False
                index += 1
                continue

            if char == "u":
                candidate = value[index + 1 : index + 5]

                if len(candidate) == 4 and re.fullmatch(r"[0-9a-fA-F]{4}", candidate):
                    result.append("\\")
                    result.append("u")
                    result.append(candidate)
                    escaped = False
                    index += 5
                    continue

                result.append("u")
                escaped = False
                index += 1
                continue

            # Invalid escape such as \[ or \*. Drop the backslash, keep char.
            result.append(char)
            escaped = False
            index += 1
            continue

        if char == "\\":
            if in_string:
                escaped = True
                index += 1
                continue

            result.append(char)
            index += 1
            continue

        if char == '"':
            result.append(char)
            in_string = not in_string
            index += 1
            continue

        if in_string:
            code = ord(char)

            if char == "\n":
                result.append("\\n")
                index += 1
                continue

            if char == "\r":
                result.append("\\r")
                index += 1
                continue

            if char == "\t":
                result.append("\\t")
                index += 1
                continue

            if code < 32:
                result.append(f"\\u{code:04x}")
                index += 1
                continue

        result.append(char)
        index += 1

    if escaped:
        result.append("\\\\")

    return "".join(result)


def _parse_model_json(text: str) -> dict[str, Any]:
    cleaned = _strip_markdown_json_fence(str(text or "").strip())

    if not cleaned:
        raise HermesArtifactError("Model returned empty output.")

    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    candidate = _extract_best_json_object(cleaned)

    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return value
    except Exception as strict_exc:
        strict_error = strict_exc

    repaired = _repair_json_string_chars(candidate)

    try:
        value = json.loads(repaired)
    except Exception as repaired_exc:
        raise HermesArtifactError(
            "Could not parse JSON from model output.\n\n"
            f"Strict parse error: {strict_error}\n"
            f"Repaired parse error: {repaired_exc}\n\n"
            f"Extracted JSON preview:\n{candidate[:3000]}\n\n"
            f"Repaired JSON preview:\n{repaired[:3000]}\n\n"
            f"Full output preview:\n{cleaned[:3000]}"
        ) from repaired_exc

    if not isinstance(value, dict):
        raise HermesArtifactError("Model JSON output must be an object.")

    return value


def _schema_instruction(artifact_format: str) -> str:
    normalized_format = normalize_artifact_format(artifact_format, default="docx")

    if normalized_format == "docx":
        return """
Return a JSON object with this exact shape:
{
  "title": "short document title",
  "body": "complete document body ready for a Word document",
  "metadata": {
    "document_kind": "report|letter|application|summary|repost|other",
    "sources": []
  }
}

DOCX writing rules:
- Write clean professional Word-document text, not markdown.
- Do not use markdown syntax like ##, ###, **bold**, or markdown tables.
- Use clear section headings as plain text.
- Use simple bullet lines with "- " when needed.
- Do not use pipe tables.
- Do not escape square brackets. Use [Residence Name], not \\[Residence Name\\].
- If personal/company details are missing, use professional placeholders.
""".strip()

    if normalized_format == "pptx":
        return """
Return a JSON object with this exact shape:
{
  "title": "short presentation title",
  "slides": [
    {
      "title": "Slide title",
      "bullets": ["bullet 1", "bullet 2", "bullet 3"]
    }
  ],
  "metadata": {
    "document_kind": "presentation",
    "sources": []
  }
}

PPTX rules:
- Return at least 5 useful slides unless the user asks for fewer.
- Each slide must have a title.
- Each slide should have 3-6 bullets.
- Do not escape square brackets. Use [Residence Name], not \\[Residence Name\\].
""".strip()

    if normalized_format == "xlsx":
        return """
Return a JSON object with this exact shape:
{
  "title": "short spreadsheet title",
  "sheets": [
    {
      "name": "Sheet name",
      "headers": ["Column A", "Column B"],
      "rows": [
        ["value A1", "value B1"],
        ["value A2", "value B2"]
      ]
    }
  ],
  "metadata": {
    "document_kind": "spreadsheet",
    "sources": []
  }
}

XLSX rules:
- Return at least one sheet.
- Every sheet must have headers.
- Rows must be arrays.
- Do not escape square brackets. Use [Residence Name], not \\[Residence Name\\].
""".strip()

    return """
Return a JSON object with this exact shape:
{
  "title": "short artifact title",
  "body": "complete text content",
  "metadata": {
    "document_kind": "text",
    "sources": []
  }
}
""".strip()


def build_artifact_prompt(
    *,
    user_prompt: str,
    artifact_format: str,
) -> str:
    normalized_format = normalize_artifact_format(artifact_format, default="docx")

    return f"""
You are the Reins artifact writer.

Create production-quality structured content for a file artifact.

Artifact format:
{normalized_format}

User request:
{user_prompt}

Critical output rules:
- Return only a valid JSON object.
- Do not include thinking text.
- Do not include markdown fences.
- Do not include explanations before or after the JSON.
- For DOCX, write clean professional Word-document text, not markdown.
- Create useful final content.
- If the user asks for a document, write the actual document.
- If the user asks for a spreadsheet, create useful tabular rows.
- If the user asks for a presentation, create useful slides.

{_schema_instruction(normalized_format)}
""".strip()


def _ollama_generate_json_api(
    *,
    prompt: str,
    timeout: int,
    debug: bool,
) -> str:
    model = os.environ.get("REINS_ARTIFACT_MODEL", "gemma4:e4b").strip()
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    url = f"{host}/api/generate"

    if not model:
        raise HermesArtifactError(
            "REINS_ARTIFACT_MODEL is empty. Set it to an Ollama model name."
        )

    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }

    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    if debug:
        print("Running artifact model API request:")
        print(f"POST {url}")
        print(f"model={model}")
        print("format=json")
        print()

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise HermesArtifactError(
            "Could not connect to Ollama API. Make sure Ollama is running.\n\n"
            "Try:\n"
            "  ollama serve\n\n"
            f"Error: {exc}"
        ) from exc
    except TimeoutError as exc:
        raise HermesArtifactError(
            f"Artifact model timed out after {timeout} seconds."
        ) from exc

    if debug:
        print("Ollama API raw response:")
        print(response_text[:5000])
        print()

    try:
        data = json.loads(response_text)
    except Exception as exc:
        raise HermesArtifactError(
            "Could not parse Ollama API response JSON.\n\n"
            f"Response preview:\n{response_text[:3000]}"
        ) from exc

    if "error" in data:
        raise HermesArtifactError(f"Ollama API error: {data['error']}")

    response_output = str(data.get("response") or "").strip()
    thinking_output = str(data.get("thinking") or "").strip()

    output = response_output or thinking_output

    if not output:
        raise HermesArtifactError(
            "Ollama API returned empty response/thinking fields.\n\n"
            f"Raw response preview:\n{response_text[:3000]}"
        )

    if debug:
        if response_output:
            print("Artifact model response field:")
            print(response_output[:5000])
            print()

        if thinking_output:
            print("Artifact model thinking field:")
            print(thinking_output[:5000])
            print()

    return output


def run_hermes_for_artifact(
    *,
    prompt: str,
    artifact_format: str,
    toolsets=None,
    timeout: int = 180,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Backwards-compatible function name.

    This uses Ollama API JSON mode, not hidden Hermes CLI.

    Hermes chat/computer-use remains for interactive agent work.
    Artifact writing uses deterministic structured local generation.
    """

    artifact_prompt = build_artifact_prompt(
        user_prompt=prompt,
        artifact_format=artifact_format,
    )

    output = _ollama_generate_json_api(
        prompt=artifact_prompt,
        timeout=timeout,
        debug=debug,
    )

    parsed = _parse_model_json(output)

    if "title" not in parsed:
        raise HermesArtifactError("Artifact response is missing required field: title")

    normalized_format = normalize_artifact_format(artifact_format, default="docx")

    if normalized_format in {"docx", "txt", "json"} and "body" not in parsed:
        raise HermesArtifactError(
            f"{normalized_format.upper()} response is missing required field: body"
        )

    if normalized_format == "pptx" and "slides" not in parsed:
        raise HermesArtifactError("PPTX response is missing required field: slides")

    if normalized_format == "xlsx" and "sheets" not in parsed:
        raise HermesArtifactError("XLSX response is missing required field: sheets")

    return parsed


def run_local_json_model(
    *,
    prompt: str,
    timeout: int = 180,
    debug: bool = False,
) -> dict[str, Any]:
    """Run the configured local artifact model with a caller-owned JSON schema."""

    output = _ollama_generate_json_api(
        prompt=prompt,
        timeout=timeout,
        debug=debug,
    )
    return _parse_model_json(output)
