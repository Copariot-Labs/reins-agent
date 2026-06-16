from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from reins.features.computer.desktop import get_desktop_backend


def _print(result: dict) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", False) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reins computer")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor")
    sub.add_parser("screenshot")

    open_parser = sub.add_parser("open")
    open_parser.add_argument("url")
    open_parser.add_argument("--app")

    open_file_parser = sub.add_parser("open-file")
    open_file_parser.add_argument("path")
    open_file_parser.add_argument("--app")

    activate_parser = sub.add_parser("activate")
    activate_parser.add_argument("app")

    type_parser = sub.add_parser("type")
    type_parser.add_argument("text")

    hotkey_parser = sub.add_parser("hotkey")
    hotkey_parser.add_argument("keys", nargs="+")

    args = parser.parse_args(list(argv or []))
    desktop = get_desktop_backend()

    if args.command == "doctor":
        return _print(desktop.doctor())

    if args.command == "screenshot":
        return _print(desktop.screenshot())

    if args.command == "open":
        return _print(desktop.open_url(args.url, app=args.app))

    if args.command == "open-file":
        return _print(desktop.open_file(args.path, app=args.app))

    if args.command == "activate":
        return _print(desktop.activate_app(args.app))

    if args.command == "type":
        return _print(desktop.type_text(args.text))

    if args.command == "hotkey":
        return _print(desktop.hotkey(*args.keys))

    parser.print_help()
    return 0