from __future__ import annotations

import argparse
import json
from typing import Sequence

from reins.features.office.content_writer import generate_office_content
from reins.features.office.service import (
    OfficeServiceError,
    create_office_document,
    list_office_documents,
    office_status,
    preview_office_document,
    revise_office_document,
)
from reins.features.office.schemas import normalize_office_format


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
        description="Create Office documents with Reins content and OfficeCLI rendering.",
    )
    subparsers = parser.add_subparsers(dest="command")

    create = subparsers.add_parser("create", help="Create a Word, Excel, or PowerPoint file.")
    create.add_argument("--format", default="docx", choices=["docx", "xlsx", "pptx", "word", "excel", "ppt"])
    create.add_argument("--prompt", required=True)
    create.add_argument("--title", default="")
    create.add_argument("--language", default="en")
    create.add_argument("--timeout", type=int, default=180)
    create.add_argument("--no-reins", action="store_true", help="Use deterministic fallback content.")
    create.add_argument("--no-hermes", action="store_true", dest="no_reins", help=argparse.SUPPRESS)
    create.add_argument("--print-content", action="store_true")
    create.add_argument("--json", action="store_true", dest="json_output")
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
    content.add_argument("--language", default="en")
    content.add_argument("--timeout", type=int, default=180)
    content.add_argument("--no-reins", action="store_true")
    content.add_argument("--no-hermes", action="store_true", dest="no_reins", help=argparse.SUPPRESS)
    content.add_argument("--json", action="store_true", dest="json_output")
    _add_presentation_arguments(content)

    revise = subparsers.add_parser("revise", help="Revise an Office file with Reins and OfficeCLI.")
    revise.add_argument("--id", required=True, dest="document_id")
    revise.add_argument("--instruction", required=True)
    revise.add_argument("--timeout", type=int, default=180)
    revise.add_argument("--json", action="store_true", dest="json_output")

    preview = subparsers.add_parser("preview", help="Render an Office file to HTML with OfficeCLI.")
    preview.add_argument("--id", required=True, dest="document_id")
    preview.add_argument("--json", action="store_true", dest="json_output")

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
            print(f"OfficeCLI available: {status['available']}")
            print(f"OfficeCLI binary: {status.get('binary') or '(not found)'}")
            if status.get("version"):
                print(f"OfficeCLI version: {status['version']}")
            if status.get("error"):
                print(f"Error: {status['error']}")
                print(f"Setup: {status['setup_hint']}")
        return 0 if status.get("available") else 1

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

    if args.command == "revise":
        try:
            record = revise_office_document(
                document_id=args.document_id,
                instruction=args.instruction,
                timeout=args.timeout,
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
                content=content,
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
