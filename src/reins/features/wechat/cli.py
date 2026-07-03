from __future__ import annotations

import argparse
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reins wechat",
        description="Reins WeChat helper commands. This is the app-specific skill layer for WeChat reliability.",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "open",
        help="Open or focus WeChat.",
    )

    search_parser = subparsers.add_parser(
        "search",
        help="Search for a WeChat contact.",
    )
    search_parser.add_argument(
        "--name",
        required=True,
        help="Contact name to search.",
    )

    draft_parser = subparsers.add_parser(
        "draft",
        help="Prepare a WeChat message draft without sending.",
    )
    draft_parser.add_argument(
        "--to",
        required=True,
        help="Contact name.",
    )
    draft_parser.add_argument(
        "--message",
        required=True,
        help="Message text to draft.",
    )

    draft_file_parser = subparsers.add_parser(
        "draft-file",
        help="Prepare a WeChat file attachment draft without sending.",
    )
    draft_file_parser.add_argument(
        "--to",
        required=True,
        help="Contact name.",
    )
    draft_file_parser.add_argument(
        "--file",
        required=True,
        help="File path to attach.",
    )
    draft_file_parser.add_argument(
        "--message",
        default="",
        help="Optional message text.",
    )

    send_parser = subparsers.add_parser(
        "send",
        help="Send a WeChat message only when --confirm is provided.",
    )
    send_parser.add_argument(
        "--to",
        required=True,
        help="Contact name.",
    )
    send_parser.add_argument(
        "--message",
        required=True,
        help="Message text.",
    )
    send_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually send the message. Without this, only a draft is prepared.",
    )

    send_file_parser = subparsers.add_parser(
        "send-file",
        help="Send a WeChat file only when --confirm is provided.",
    )
    send_file_parser.add_argument(
        "--to",
        required=True,
        help="Contact name.",
    )
    send_file_parser.add_argument(
        "--file",
        required=True,
        help="File path to attach.",
    )
    send_file_parser.add_argument(
        "--message",
        default="",
        help="Optional message text.",
    )
    send_file_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually send the file. Without this, only a draft is prepared.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv or []))

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "open":
        print("WeChat skill placeholder: open/focus WeChat will be implemented in Phase 5.")
        return 0

    if args.command == "search":
        print(f"WeChat skill placeholder: search contact `{args.name}` will be implemented in Phase 5.")
        return 0

    if args.command == "draft":
        print(f"WeChat skill placeholder: draft message to `{args.to}`.")
        print("Message was NOT sent.")
        print(f"Message: {args.message}")
        return 0

    if args.command == "draft-file":
        print(f"WeChat skill placeholder: draft file message to `{args.to}`.")
        print("File was NOT sent.")
        print(f"File: {args.file}")
        if args.message:
            print(f"Message: {args.message}")
        return 0

    if args.command == "send":
        if not args.confirm:
            print("Missing --confirm. Drafting only.")
            print(f"Draft message to `{args.to}`.")
            print("Message was NOT sent.")
            print(f"Message: {args.message}")
            return 0

        print(f"WeChat skill placeholder: confirmed send to `{args.to}` will be implemented later.")
        return 0

    if args.command == "send-file":
        if not args.confirm:
            print("Missing --confirm. Drafting file only.")
            print(f"Draft file message to `{args.to}`.")
            print("File was NOT sent.")
            print(f"File: {args.file}")
            if args.message:
                print(f"Message: {args.message}")
            return 0

        print(f"WeChat skill placeholder: confirmed file send to `{args.to}` will be implemented later.")
        print(f"File: {args.file}")
        return 0

    parser.print_help()
    return 1