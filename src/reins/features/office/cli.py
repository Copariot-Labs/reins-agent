from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from reins.features.office.content_writer import (
    DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    generate_office_content,
)
from reins.features.office.intent import classify_office_followup
from reins.features.office.service import (
    OfficeServiceError,
    create_office_document,
    import_office_document,
    list_office_documents,
    office_status,
    preview_office_document,
    revise_office_document,
)
from reins.features.office.schemas import normalize_office_format
from reins.features.office.workflows import list_office_workflows


_PROGRESS_PREFIX = "REINS_OFFICE_PROGRESS "


def _progress_reporter(enabled: bool):
    if not enabled:
        return None

    def report(stage: str, percent: int, message_zh: str, message_en: str) -> None:
        payload = {
            "stage": stage,
            "percent": percent,
            "message_zh": message_zh,
            "message_en": message_en,
        }
        print(
            _PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=False),
            file=sys.stderr,
            flush=True,
        )

    return report


def _add_presentation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ppt-style",
        default="auto",
        choices=["auto", "executive", "modern", "bold", "minimal"],
    )
    parser.add_argument("--slide-count", type=int, default=8)
    parser.add_argument(
        "--audience",
        default="general",
        choices=["general", "executive", "client", "team"],
    )
    parser.add_argument(
        "--detail",
        default="balanced",
        choices=["concise", "balanced", "detailed"],
    )


def _presentation_options(args: argparse.Namespace) -> dict[str, object]:
    return {
        "style": args.ppt_style,
        "slide_count": args.slide_count,
        "audience": args.audience,
        "detail": args.detail,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reins office",
        description="Create Office documents with Reins.",
    )
    subparsers = parser.add_subparsers(dest="command")

    create = subparsers.add_parser("create", help="Create a Word, Excel, or PowerPoint file.")
    create.add_argument("--format", default="docx", choices=["docx", "xlsx", "pptx", "word", "excel", "ppt"])
    create.add_argument("--prompt", required=True)
    create.add_argument("--title", default="")
    create.add_argument("--language", default="zh")
    create.add_argument("--skill", default="", dest="skill_id")
    create.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    )
    create.add_argument("--no-reins", action="store_true", help="Use deterministic fallback content.")
    create.add_argument("--no-hermes", action="store_true", dest="no_reins", help=argparse.SUPPRESS)
    create.add_argument("--print-content", action="store_true")
    create.add_argument("--json", action="store_true", dest="json_output")
    create.add_argument("--progress", action="store_true", help=argparse.SUPPRESS)
    _add_presentation_arguments(create)

    list_cmd = subparsers.add_parser("list", help="List created Office documents.")
    list_cmd.add_argument("--limit", type=int, default=25)
    list_cmd.add_argument("--format", default="")
    list_cmd.add_argument("--json", action="store_true", dest="json_output")

    doctor = subparsers.add_parser("doctor", help="Check Office feature dependencies.")
    doctor.add_argument("--json", action="store_true", dest="json_output")

    content = subparsers.add_parser("content", help="Generate Office content JSON without rendering.")
    content.add_argument("--format", default="docx", choices=["docx", "xlsx", "pptx", "word", "excel", "ppt"])
    content.add_argument("--prompt", required=True)
    content.add_argument("--title", default="")
    content.add_argument("--language", default="zh")
    content.add_argument("--skill", default="", dest="skill_id")
    content.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    )
    content.add_argument("--no-reins", action="store_true")
    content.add_argument("--no-hermes", action="store_true", dest="no_reins", help=argparse.SUPPRESS)
    content.add_argument("--json", action="store_true", dest="json_output")
    _add_presentation_arguments(content)

    skills = subparsers.add_parser("skills", help="List fixed Reins Office workflows.")
    skills.add_argument("--format", default="")
    skills.add_argument("--json", action="store_true", dest="json_output")

    revise = subparsers.add_parser("revise", help="Revise an Office file with Reins.")
    revise.add_argument("--id", required=True, dest="document_id")
    revise.add_argument("--instruction", required=True)
    revise.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_OFFICE_CONTENT_TIMEOUT_SECONDS,
    )
    revise.add_argument("--json", action="store_true", dest="json_output")
    revise.add_argument("--progress", action="store_true", help=argparse.SUPPRESS)

    preview = subparsers.add_parser("preview", help="Render an Office file preview with Reins.")
    preview.add_argument("--id", required=True, dest="document_id")
    preview.add_argument("--json", action="store_true", dest="json_output")

    import_cmd = subparsers.add_parser(
        "import", help="Import an existing Office file."
    )
    import_cmd.add_argument("--source", required=True)
    import_cmd.add_argument("--format", required=True, choices=["docx", "xlsx", "pptx"])
    import_cmd.add_argument("--name", default="")
    import_cmd.add_argument("--json", action="store_true", dest="json_output")

    route = subparsers.add_parser("route", help=argparse.SUPPRESS)
    route.add_argument("--message", required=True)
    route.add_argument("--document-title", required=True)
    route.add_argument("--document-kind", required=True)
    route.add_argument("--timeout", type=int, default=45)
    route.add_argument("--json", action="store_true", dest="json_output")

    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _print_record(record) -> None:
    _print_json(record.to_dict())


def _print_record_human(record) -> None:
    print("Office document created.")
    print(f"Title: {record.title}")
    print(f"Type: {record.kind}")
    print(f"Path: {record.path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv or []))

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "doctor":
        status = office_status()
        if args.json_output:
            _print_json(status)
        else:
            print(f"Reins Office available: {status['available']}")
            if status.get("version"):
                print(f"Reins Office version: {status['version']}")
            if status.get("error"):
                print(f"Error: {status['error']}")
                print(f"Setup: {status['setup_hint']}")
        return 0 if status.get("available") else 1

    if args.command == "skills":
        workflows = list_office_workflows(office_format=args.format or None)
        if args.json_output:
            _print_json({"skills": workflows})
        else:
            for workflow in workflows:
                print(f"{workflow['format'].upper()}  {workflow['id']}  {workflow['label_zh']}")
        return 0

    if args.command == "route":
        try:
            decision = classify_office_followup(
                message=args.message,
                document_title=args.document_title,
                document_kind=args.document_kind,
                timeout=args.timeout,
            )
        except Exception as exc:
            if args.json_output:
                _print_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )
            else:
                print(f"Office routing failed: {exc}")
            return 1
        if args.json_output:
            _print_json({"ok": True, "decision": decision})
        else:
            _print_json(decision)
        return 0

    if args.command == "content":
        try:
            content = generate_office_content(
                prompt=args.prompt,
                office_format=normalize_office_format(args.format),
                title=args.title or None,
                language=args.language,
                timeout=args.timeout,
                use_reins=not args.no_reins,
                presentation_options=_presentation_options(args),
                skill_id=args.skill_id or None,
            )
        except Exception as exc:
            if args.json_output:
                _print_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )
            else:
                print(f"Office content generation failed: {exc}")
            return 1

        if args.json_output:
            _print_json({"ok": True, "content": content})
        else:
            _print_json(content)
        return 0

    if args.command == "list":
        records = list_office_documents(
            limit=args.limit,
            kind=args.format or None,
        )
        if args.json_output:
            _print_json({"documents": [record.to_dict() for record in records]})
        else:
            if not records:
                print("No Office documents found.")
            for record in records:
                print(f"{record.created_at}  {record.kind.upper()}  {record.title}  {record.path}")
        return 0

    if args.command == "preview":
        try:
            preview_path = preview_office_document(args.document_id)
        except Exception as exc:
            if args.json_output:
                _print_json({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
            else:
                print(f"Office preview failed: {exc}")
            return 1
        if args.json_output:
            _print_json({"ok": True, "preview_path": str(preview_path)})
        else:
            print(preview_path)
        return 0

    if args.command == "import":
        try:
            record = import_office_document(
                source_path=args.source,
                office_format=args.format,
                display_name=args.name or None,
            )
        except Exception as exc:
            if args.json_output:
                _print_json({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
            else:
                print(f"Office import failed: {exc}")
            return 1
        if args.json_output:
            _print_json({"ok": True, "document": record.to_dict()})
        else:
            print("Office document imported.")
            print(f"Title: {record.title}")
            print(f"Type: {record.kind}")
            print(f"Path: {record.path}")
        return 0

    if args.command == "revise":
        try:
            record = revise_office_document(
                document_id=args.document_id,
                instruction=args.instruction,
                timeout=args.timeout,
                progress=_progress_reporter(args.progress),
            )
        except Exception as exc:
            if args.json_output:
                _print_json({"ok": False, "error": str(exc), "error_type": type(exc).__name__})
            else:
                print(f"Office revision failed: {exc}")
            return 1
        if args.json_output:
            _print_json({"ok": True, "document": record.to_dict()})
        else:
            _print_record_human(record)
        return 0

    if args.command == "create":
        try:
            content = None
            if args.print_content:
                content = generate_office_content(
                    prompt=args.prompt,
                    office_format=normalize_office_format(args.format),
                    title=args.title or None,
                    language=args.language,
                    timeout=args.timeout,
                    use_reins=not args.no_reins,
                    presentation_options=_presentation_options(args),
                    skill_id=args.skill_id or None,
                )
                print("Office content:")
                _print_json(content)
                print()

            record = create_office_document(
                prompt=args.prompt,
                office_format=normalize_office_format(args.format),
                title=args.title or None,
                language=args.language,
                timeout=args.timeout,
                use_reins=not args.no_reins,
                presentation_options=_presentation_options(args),
                skill_id=args.skill_id or None,
                content=content,
                progress=_progress_reporter(args.progress),
            )
        except (OfficeServiceError, Exception) as exc:
            if args.json_output:
                _print_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                )
            else:
                print(f"Office creation failed: {exc}")
            return 1

        if args.json_output:
            _print_json({"ok": True, "document": record.to_dict()})
        else:
            _print_record_human(record)
        return 0

    parser.print_help()
    return 1
