from __future__ import annotations

import sys
from typing import Sequence

from reins.compat.env import prepare_env


REINS_OWNED_COMMANDS = {
    "version",
    "about",
    "update",
    "migrate",
    "finance",
    "debug-env",
}


PASS_THROUGH_COMMANDS = {
    "chat",
    "model",
    "fallback",
    "secrets",
    "gateway",
    "proxy",
    "lsp",
    "setup",
    "postinstall",
    "whatsapp",
    "slack",
    "send",
    "login",
    "logout",
    "auth",
    "status",
    "cron",
    "webhook",
    "portal",
    "kanban",
    "hooks",
    "doctor",
    "security",
    "dump",
    "debug",
    "backup",
    "checkpoints",
    "import",
    "config",
    "pairing",
    "skills",
    "bundles",
    "plugins",
    "curator",
    "memory",
    "tools",
    "computer-use",
    "mcp",
    "sessions",
    "insights",
    "claw",
    "uninstall",
    "acp",
    "profile",
    "completion",
    "dashboard",
    "logs",
}


def print_reins_help() -> None:
    print(
        """Reins

Usage:
  reins [command] [options]

Core commands:
  reins chat
  reins model
  reins tools
  reins config
  reins gateway
  reins setup
  reins doctor
  reins cron
  reins sessions

Reins commands:
  reins version
  reins about
  reins migrate hermes
  reins update
  reins finance
  reins debug-env

Examples:
  reins chat
  reins doctor
  reins model
  reins finance --help
  REINS_HOME=/tmp/reins-test reins debug-env

Environment:
  REINS_HOME   Reins data directory, defaults to ~/.reins
"""
    )


def print_unknown_command(command: str) -> None:
    print(f"Unknown Reins command: {command}")
    print()
    print("Run `reins --help` to see available commands.")


def handle_reins_owned_command(argv: Sequence[str]) -> int:
    command = argv[0] if argv else ""

    if command == "version":
        from reins.compat.version import print_version

        return print_version()

    if command == "about":
        from reins.compat.about import print_about

        return print_about()

    if command == "debug-env":
        from reins.compat.env import describe_env

        env = describe_env()

        print(f"REINS_HOME={env['REINS_HOME']}")
        print(f"HERMES_HOME={env['HERMES_HOME']}")
        print(f"resolved_reins_home={env['resolved_reins_home']}")
        return 0

    if command == "migrate":
        if len(argv) < 2:
            print("Usage: reins migrate hermes [--force]")
            return 1

        target = argv[1]
        force = "--force" in argv[2:]

        if target != "hermes":
            print(f"Unknown migration target: {target}")
            print("Usage: reins migrate hermes [--force]")
            return 1

        from reins.compat.migrate import MigrationError, migrate_hermes_to_reins

        try:
            return migrate_hermes_to_reins(force=force)
        except MigrationError as exc:
            print(f"Migration failed: {exc}")
            return 1

    if command == "update":
        dry_run = "--dry-run" in argv[1:]

        from reins.compat.update import UpdateError, update_reins

        try:
            return update_reins(dry_run=dry_run)
        except UpdateError as exc:
            print(f"Update failed: {exc}")
            return 1

    if command == "finance":
        from reins.features.finance.cli import main as finance_main

        return finance_main(argv[1:])

    print_unknown_command(command)

    return 1

# 
def maybe_preprocess_chat(argv: Sequence[str]) -> int | None:
    if not argv:
        return None

    if argv[0] != "chat":
        return None

    # Only intercept direct prompt style:
    #   reins chat "今天买咖啡 28"
    #
    # Do not intercept interactive chat:
    #   reins chat
    #
    # Do not intercept flag-heavy Hermes chat calls:
    #   reins chat --help
    #   reins chat --model ...
    if len(argv) < 2:
        return None

    message_parts = list(argv[1:])

    if any(part.startswith("-") for part in message_parts):
        return None

    message = " ".join(message_parts).strip()

    if not message:
        return None

    from reins.features.finance.plugin import preprocess_finance_text

    result = preprocess_finance_text(message)

    if not result.handled:
        return None

    print(result.message)
    return result.exit_code


def normalize_hermes_argv(argv: Sequence[str]) -> list[str]:
    if not argv:
        return list(argv)

    if argv[0] != "chat":
        return list(argv)

    # Keep interactive chat unchanged:
    #   reins chat
    if len(argv) == 1:
        return list(argv)

    message_parts = list(argv[1:])

    # Keep flag-heavy Hermes usage unchanged:
    #   reins chat --help
    #   reins chat --model ...
    if any(part.startswith("-") for part in message_parts):
        return list(argv)

    message = " ".join(message_parts).strip()

    if not message:
        return ["chat"]

    # Hermes expects prompt through global -z before the subcommand.
    return ["-z", message, "chat"]


def run_hermes(argv: Sequence[str]) -> int:
    from hermes_cli.main import main as hermes_main

    hermes_argv = normalize_hermes_argv(argv)

    # Hermes sees argv as if the user typed `hermes ...`.
    sys.argv = ["hermes", *hermes_argv]

    result = hermes_main()

    if isinstance(result, int):
        return result

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    prepare_env()

    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in {"-h", "--help", "help"}:
        print_reins_help()
        return 0

    command = argv[0]

    if command in REINS_OWNED_COMMANDS:
        return handle_reins_owned_command(argv)

    if command in PASS_THROUGH_COMMANDS:
        preprocessed = maybe_preprocess_chat(argv)

        if preprocessed is not None:
            return preprocessed

        return run_hermes(argv)

    if command.startswith("-"):
        if command in {"-h", "--help"}:
            print_reins_help()
            return 0

        return run_hermes(argv)

    print_unknown_command(command)
    return 1