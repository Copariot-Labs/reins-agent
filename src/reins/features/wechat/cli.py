from __future__ import annotations

import argparse
import json
from typing import Any, Sequence

from reins.features.wechat.plugin_installer import install_hermes_plugin, print_install_instructions
from reins.features.wechat.service import (
    doctor,
    draft_file,
    draft_message,
    exit_code_for_result,
    open_wechat,
    search_contact,
    send_current_draft,
    send_file,
    send_message,
)


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print a machine-readable JSON result.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the automation plan without running OS commands.",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reins wechat",
        description="Deterministic Reins WeChat desktop automation for macOS and Linux.",
    )

    common = _common_parser()
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "doctor",
        parents=[common],
        help="Check deterministic WeChat automation dependencies.",
    )

    subparsers.add_parser(
        "open",
        parents=[common],
        help="Open or focus WeChat.",
    )

    search_parser = subparsers.add_parser(
        "search",
        parents=[common],
        help="Search for a WeChat contact.",
    )
    search_parser.add_argument("--name", required=True, help="Contact name to search.")

    draft_parser = subparsers.add_parser(
        "draft",
        parents=[common],
        help="Prepare a WeChat message draft without sending.",
    )
    draft_parser.add_argument("--to", required=True, help="Contact name.")
    draft_parser.add_argument("--message", required=True, help="Message text to draft.")

    draft_file_parser = subparsers.add_parser(
        "draft-file",
        parents=[common],
        help="Prepare a WeChat file attachment draft without sending.",
    )
    draft_file_parser.add_argument("--to", required=True, help="Contact name.")
    draft_file_parser.add_argument("--file", required=True, help="File path to attach.")
    draft_file_parser.add_argument("--message", default="", help="Optional message text.")

    send_parser = subparsers.add_parser(
        "send",
        parents=[common],
        help="Draft and send a WeChat message only when --confirm is provided.",
    )
    send_parser.add_argument("--to", required=True, help="Contact name.")
    send_parser.add_argument("--message", required=True, help="Message text.")
    send_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually send the message. Without this, only a draft is prepared.",
    )
    send_parser.add_argument(
        "--send-key",
        default="enter",
        help="Send shortcut to use after confirmation. Supported: enter, cmd-enter (macOS), ctrl-enter (Linux).",
    )

    send_current_parser = subparsers.add_parser(
        "send-current",
        parents=[common],
        help="Send the currently focused WeChat draft only when --confirm is provided.",
    )
    send_current_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually send the current draft.",
    )
    send_current_parser.add_argument(
        "--send-key",
        default="enter",
        help="Send shortcut to use after confirmation. Supported: enter, cmd-enter (macOS), ctrl-enter (Linux).",
    )

    send_file_parser = subparsers.add_parser(
        "send-file",
        parents=[common],
        help="Draft and send a WeChat file only when --confirm is provided.",
    )
    send_file_parser.add_argument("--to", required=True, help="Contact name.")
    send_file_parser.add_argument("--file", required=True, help="File path to attach.")
    send_file_parser.add_argument("--message", default="", help="Optional message text.")
    send_file_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually send the file. Without this, only a draft is prepared.",
    )
    send_file_parser.add_argument(
        "--send-key",
        default="enter",
        help="Send shortcut to use after confirmation. Supported: enter, cmd-enter (macOS), ctrl-enter (Linux).",
    )

    subparsers.add_parser(
        "install-plugin",
        help="Install the Hermes plugin wrapper for deterministic WeChat tools.",
    )

    return parser


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _print_human(result: dict[str, Any]) -> None:
    status = "OK" if result.get("ok") else "FAILED"
    print(f"{status}: {result.get('message') or result.get('action')}")
    if result.get("contact"):
        print(f"Contact: {result['contact']}")
    if result.get("file"):
        print(f"File: {result['file']}")
    if result.get("draft_only"):
        print("Draft only: yes")
    if result.get("sent"):
        print("Sent: yes")
    elif result.get("action", "").startswith("send"):
        print("Sent: no")
    for warning in result.get("warnings") or []:
        print(f"Warning: {warning}")
    if result.get("error"):
        print(f"Error: {result['error']}")


def _finish(result: dict[str, Any], *, json_output: bool) -> int:
    if json_output:
        _print_json(result)
    else:
        _print_human(result)
    return exit_code_for_result(result)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "install-plugin":
        plugin_dir = install_hermes_plugin()
        print_install_instructions(plugin_dir)
        return 0

    json_output = bool(getattr(args, "json_output", False))
    dry_run = bool(getattr(args, "dry_run", False))

    if args.command == "doctor":
        return _finish(doctor(dry_run=dry_run), json_output=json_output)

    if args.command == "open":
        return _finish(open_wechat(dry_run=dry_run), json_output=json_output)

    if args.command == "search":
        return _finish(search_contact(args.name, dry_run=dry_run), json_output=json_output)

    if args.command == "draft":
        return _finish(draft_message(args.to, args.message, dry_run=dry_run), json_output=json_output)

    if args.command == "draft-file":
        return _finish(draft_file(args.to, args.file, args.message, dry_run=dry_run), json_output=json_output)

    if args.command == "send":
        return _finish(
            send_message(args.to, args.message, confirm=args.confirm, send_key=args.send_key, dry_run=dry_run),
            json_output=json_output,
        )

    if args.command == "send-current":
        return _finish(
            send_current_draft(confirm=args.confirm, send_key=args.send_key, dry_run=dry_run),
            json_output=json_output,
        )

    if args.command == "send-file":
        return _finish(
            send_file(args.to, args.file, args.message, confirm=args.confirm, send_key=args.send_key, dry_run=dry_run),
            json_output=json_output,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
