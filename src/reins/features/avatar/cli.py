from __future__ import annotations

import json
from typing import Sequence

from reins.features.avatar.integration import (
    build_companion_config,
    build_companion_production,
    get_avatar_status,
    install_avatar_bridge,
    install_companion_dependencies,
    run_companion_development,
    uninstall_avatar_bridge,
)


def print_help() -> None:
    print(
        """Reins Avatar

Usage:
  reins avatar [command]

Commands:
  install             Install the stable Reins ACP bridge
  uninstall           Remove generated bridge files
  doctor              Check avatar integration readiness
  doctor --json       Print readiness as JSON
  config              Show resolved companion configuration
  config --json       Show configuration as JSON
  dependencies        Install companion npm dependencies
  dev                 Start companion in Tauri development mode
  build               Build the production companion application

Examples:
  reins avatar install
  reins avatar doctor
  reins avatar dependencies
  reins avatar dev
  reins avatar build
"""
    )


def handle_install() -> int:
    launcher_path = install_avatar_bridge()
    config = build_companion_config(
        launcher_path
    )

    print("Reins avatar bridge installed.")
    print()
    print(f"Launcher: {launcher_path}")
    print(f"REINS_HOME: {config['reins_home']}")
    print(
        "Companion source: "
        f"{config['companion_source']}"
    )
    print()
    print("Next command:")
    print("  reins avatar doctor")

    return 0


def handle_uninstall() -> int:
    removed = uninstall_avatar_bridge()

    if removed:
        print(
            "Reins avatar bridge removed."
        )
    else:
        print(
            "Reins avatar bridge was not installed."
        )

    return 0


def handle_doctor(
    arguments: Sequence[str],
) -> int:
    status = get_avatar_status()

    if "--json" in arguments:
        print(
            json.dumps(
                status.to_dict(),
                ensure_ascii=False,
                indent=2,
            )
        )

        return (
            0
            if status.bridge_ready
            else 1
        )

    print("Reins Avatar Doctor")
    print()

    print(
        "Bridge ready: "
        f"{'yes' if status.bridge_ready else 'no'}"
    )

    print(
        "Development ready: "
        f"{'yes' if status.development_ready else 'no'}"
    )

    print()

    print(
        f"REINS_HOME: {status.reins_home}"
    )

    print(
        f"Project root: {status.project_root}"
    )

    print(
        "Companion source: "
        f"{status.companion_source}"
    )

    print(
        "Companion source exists: "
        f"{'yes' if status.companion_source_exists else 'no'}"
    )

    print(
        "Companion package exists: "
        f"{'yes' if status.companion_package_exists else 'no'}"
    )

    print(
        f"Runtime Python: {status.runtime_python}"
    )

    print(
        "Runtime Python exists: "
        f"{'yes' if status.runtime_python_exists else 'no'}"
    )

    print(
        f"ACP launcher: {status.launcher_path}"
    )

    print(
        "ACP launcher exists: "
        f"{'yes' if status.launcher_exists else 'no'}"
    )

    print(
        "ACP launcher executable: "
        f"{'yes' if status.launcher_executable else 'no'}"
    )

    print(
        "Hermes ACP adapter: "
        f"{'available' if status.hermes_acp_adapter_available else 'missing'}"
    )

    print(
        "npm available: "
        f"{'yes' if status.npm_available else 'no'}"
    )

    print(
        "node_modules installed: "
        f"{'yes' if status.node_modules_installed else 'no'}"
    )

    print()
    print(status.message)

    return (
        0
        if status.bridge_ready
        else 1
    )


def handle_config(
    arguments: Sequence[str],
) -> int:
    config = build_companion_config()

    if "--json" in arguments:
        print(
            json.dumps(
                config,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    print(
        "Reins Agent Companion configuration"
    )

    print()

    print(
        f"Preset: {config['preset']}"
    )

    print(
        f"Protocol: {config['protocol']}"
    )

    print(
        f"Transport: {config['transport']}"
    )

    print(
        f"Program: {config['program']}"
    )

    print("Arguments: none")

    print(
        f"REINS_HOME: {config['reins_home']}"
    )

    print(
        "Companion source: "
        f"{config['companion_source']}"
    )

    return 0


def main(
    argv: Sequence[str] | None = None,
) -> int:
    arguments = list(argv or [])

    if (
        not arguments
        or arguments[0]
        in {
            "help",
            "-h",
            "--help",
        }
    ):
        print_help()
        return 0

    command = arguments[0]
    command_arguments = arguments[1:]

    try:
        if command == "install":
            return handle_install()

        if command == "uninstall":
            return handle_uninstall()

        if command == "doctor":
            return handle_doctor(
                command_arguments
            )

        if command == "config":
            return handle_config(
                command_arguments
            )

        if command == "dependencies":
            return (
                install_companion_dependencies()
            )

        if command == "dev":
            return (
                run_companion_development()
            )

        if command == "build":
            return (
                build_companion_production()
            )

    except RuntimeError as exc:
        print(
            f"Avatar command failed: {exc}"
        )
        return 1

    print(
        f"Unknown avatar command: {command}"
    )

    print(
        "Run `reins avatar --help` "
        "for available commands."
    )

    return 1