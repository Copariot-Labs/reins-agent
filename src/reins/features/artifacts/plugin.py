from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from reins.features.artifacts.hermes_writer import HermesArtifactError, run_hermes_for_artifact
from reins.features.artifacts.office import create_office_artifact


@dataclass(slots=True)
class ArtifactPreprocessResult:
    handled: bool
    message: str = ""
    exit_code: int = 0
    artifact: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "handled": self.handled,
            "message": self.message,
            "exit_code": self.exit_code,
            "artifact": self.artifact,
        }


DOCUMENT_KEYWORDS = {
    "document",
    "doc",
    "docx",
    "letter",
    "application",
    "report",
    "proposal",
    "summary",
    "resume",
    "cv",
    "notice",
    "program",
    "plan",
    "minutes",
    "memo",
    "policy",
    "agreement",
    "contract",
    "statement",
    "certificate",
    "form",
    "invoice",
    "receipt",
    "agenda",
    "event plan",
    "meeting note",
    "meeting notes",
    "business plan",
    "project plan",
    "case report",
    "work order",
    "announcement",
    "invitation",
    "official letter",
    "cover letter",
    "recommendation letter",
    "complaint letter",
    "leave letter",
    "application letter",
}

PRESENTATION_KEYWORDS = {
    "presentation",
    "ppt",
    "pptx",
    "slides",
    "slide deck",
    "deck",
    "powerpoint",
    "pitch deck",
    "training slides",
    "meeting slides",
    "proposal deck",
    "presentation deck",
}

SPREADSHEET_KEYWORDS = {
    "spreadsheet",
    "excel",
    "xlsx",
    "sheet",
    "table",
    "ledger",
    "tracker",
    "budget",
    "inventory",
    "schedule table",
    "expense sheet",
    "cost sheet",
    "price list",
    "attendance sheet",
    "maintenance tracker",
    "task tracker",
    "repair tracker",
    "payment tracker",
    "financial report",
    "monthly report table",
    "staff roster",
    "resident list",
}

CREATE_KEYWORDS = {
    "create",
    "make",
    "generate",
    "write",
    "prepare",
    "draft",
    "build",
    "compose",
    "produce",
    "design",
    "make me",
    "write me",
    "prepare me",
    "draft me",
    "generate me",
}

QUESTION_PATTERNS = [
    r"^how\s+to\s+",
    r"^how\s+can\s+i\s+",
    r"^what\s+is\s+",
    r"^why\s+",
    r"^can\s+you\s+explain\s+",
]


def _contains_any(message: str, keywords: set[str]) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in keywords)


def infer_artifact_format(message: str) -> str | None:
    lowered = message.lower()

    if _contains_any(lowered, PRESENTATION_KEYWORDS):
        return "pptx"

    if _contains_any(lowered, SPREADSHEET_KEYWORDS):
        return "xlsx"

    if _contains_any(lowered, DOCUMENT_KEYWORDS):
        return "docx"

    return None


def should_handle_artifact_chat(message: str) -> bool:
    lowered = message.lower().strip()

    if not lowered:
        return False

    if any(re.search(pattern, lowered) for pattern in QUESTION_PATTERNS):
        return False

    has_create_intent = _contains_any(lowered, CREATE_KEYWORDS)
    inferred_format = infer_artifact_format(lowered)

    if not has_create_intent:
        return False

    if inferred_format is None:
        return False

    return True


def _format_success_message(*, title: str, kind: str, path: str) -> str:
    return "\n".join(
        [
            "Artifact created successfully.",
            f"Title: {title}",
            f"Type: {kind}",
            f"Path: {path}",
            "",
            "Open it with:",
            f'open "{path}"',
        ]
    )


def preprocess_artifact_text(
    message: str,
    *,
    verbose: bool = True,
) -> ArtifactPreprocessResult:
    if not should_handle_artifact_chat(message):
        return ArtifactPreprocessResult(handled=False)

    artifact_format = infer_artifact_format(message) or "docx"

    if verbose:
        print(f"Reins artifact request detected. Format: {artifact_format}")
        print("Generating structured artifact content...")
        print()

    try:
        content = run_hermes_for_artifact(
            prompt=message,
            artifact_format=artifact_format,
            toolsets=[],
            timeout=180,
            debug=False,
        )
    except HermesArtifactError as exc:
        return ArtifactPreprocessResult(
            handled=True,
            exit_code=1,
            message=f"Failed to generate artifact content: {exc}",
        )

    title = str(content.get("title") or "Reins Artifact").strip()
    body = content.get("body", "")

    metadata = dict(content.get("metadata") or {})
    metadata["generated_by"] = "artifact-model"
    metadata["source_prompt"] = message
    metadata["triggered_from"] = "reins-chat-preprocessor"

    try:
        record = create_office_artifact(
            title=title,
            body=body,
            artifact_format=artifact_format,
            sheets=content.get("sheets"),
            slides=content.get("slides"),
            metadata=metadata,
            source="reins-chat",
        )
    except Exception as exc:
        return ArtifactPreprocessResult(
            handled=True,
            exit_code=1,
            message=f"Failed to create artifact file: {exc}",
        )

    return ArtifactPreprocessResult(
        handled=True,
        message=_format_success_message(
            title=record.title,
            kind=record.kind,
            path=record.path,
        ),
        exit_code=0,
        artifact=record.to_dict(),
    )
