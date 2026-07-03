from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from reins.features.artifacts.hermes_writer import HermesArtifactError, run_hermes_for_artifact
from reins.features.artifacts.office import create_office_artifact
from reins.features.artifacts.plugin import preprocess_artifact_text
from reins.features.artifacts.store import get_default_artifact_store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reins artifacts",
        description="Create and inspect Reins artifacts.",
    )

    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser(
        "create",
        help="Create an artifact from direct input.",
    )
    create_parser.add_argument(
        "--format",
        default="docx",
        choices=["docx", "xlsx", "pptx", "txt", "json"],
        help="Artifact format.",
    )
    create_parser.add_argument(
        "--title",
        required=True,
        help="Artifact title.",
    )
    create_parser.add_argument(
        "--body",
        default="",
        help="Artifact body text.",
    )
    create_parser.add_argument(
        "--json",
        dest="json_payload",
        default="",
        help="JSON payload string or path for sheets/slides/metadata.",
    )

    hermes_parser = subparsers.add_parser(
        "from-hermes",
        help="Generate artifact content with the configured artifact model, then create the file.",
    )
    hermes_parser.add_argument(
        "--format",
        default="docx",
        choices=["docx", "xlsx", "pptx", "txt", "json"],
        help="Artifact format.",
    )
    hermes_parser.add_argument(
        "--prompt",
        required=True,
        help="Task prompt for Hermes.",
    )
    hermes_parser.add_argument(
        "--toolset",
        action="append",
        default=[],
        help="Hermes toolset to enable, for example: browser or computer_use.",
    )
    hermes_parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Hermes timeout in seconds.",
    )
    hermes_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print Hermes command/stdout/stderr previews.",
    )
    hermes_parser.add_argument(
        "--print-content",
        action="store_true",
        help="Print Hermes structured content before creating the artifact.",
    )

    preprocess_parser = subparsers.add_parser(
        "preprocess-chat",
        help="Run the artifact chat preprocessor for a single message.",
    )
    preprocess_parser.add_argument(
        "--message",
        required=True,
        help="Chat message to inspect and optionally handle.",
    )
    preprocess_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print a machine-readable result.",
    )

    list_parser = subparsers.add_parser(
        "list",
        help="List artifacts.",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum records to show.",
    )
    list_parser.add_argument(
        "--kind",
        default=None,
        help="Filter by artifact kind.",
    )

    latest_parser = subparsers.add_parser(
        "latest",
        help="Show latest artifact.",
    )
    latest_parser.add_argument(
        "--kind",
        default=None,
        help="Filter by artifact kind.",
    )

    return parser


def _load_payload(raw: str) -> dict:
    if not raw:
        return {}

    path = Path(raw)

    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    return json.loads(raw)


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _print_record(record) -> None:
    _print_json(record.to_dict())


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv or []))

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "create":
        payload = _load_payload(args.json_payload)

        record = create_office_artifact(
            title=args.title,
            body=args.body or payload.get("body", ""),
            artifact_format=args.format,
            sheets=payload.get("sheets"),
            slides=payload.get("slides"),
            metadata=payload.get("metadata"),
            source="reins-cli",
        )

        _print_record(record)
        return 0

    if args.command == "from-hermes":
        try:
            content = run_hermes_for_artifact(
                prompt=args.prompt,
                artifact_format=args.format,
                toolsets=args.toolset,
                timeout=args.timeout,
                debug=args.debug,
            )
        except HermesArtifactError as exc:
            print(f"Failed to generate artifact content: {exc}")
            return 1

        if args.print_content:
            print("Hermes structured content:")
            _print_json(content)
            print()

        title = str(content.get("title") or "Hermes Artifact").strip()
        body = content.get("body", "")

        metadata = dict(content.get("metadata") or {})
        metadata["generated_by"] = "hermes"
        metadata["source_prompt"] = args.prompt
        metadata["toolsets"] = list(args.toolset or [])

        record = create_office_artifact(
            title=title,
            body=body,
            artifact_format=args.format,
            sheets=content.get("sheets"),
            slides=content.get("slides"),
            metadata=metadata,
            source="hermes",
        )

        _print_record(record)
        return 0

    if args.command == "preprocess-chat":
        result = preprocess_artifact_text(
            args.message,
            verbose=not args.json_output,
        )

        if args.json_output:
            _print_json(result.to_dict())
        elif result.handled and result.message:
            print(result.message)

        return result.exit_code if result.handled else 0

    store = get_default_artifact_store()

    if args.command == "list":
        records = store.list(limit=args.limit, kind=args.kind)

        for record in records:
            _print_record(record)

        return 0

    if args.command == "latest":
        record = store.latest(kind=args.kind)

        if record is None:
            print("No artifact found.")
            return 1

        _print_record(record)
        return 0

    parser.print_help()
    return 1
