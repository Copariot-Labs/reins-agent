from __future__ import annotations

import subprocess
from pathlib import Path

from reins import __version__
from reins.compat.bootstrap import get_project_root, get_vendor_hermes_path


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def get_git_commit(path: Path) -> str | None:
    return _run_git(["rev-parse", "--short", "HEAD"], cwd=path)


def get_git_branch(path: Path) -> str | None:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path)


def get_hermes_version() -> str | None:
    try:
        import importlib.metadata

        return importlib.metadata.version("hermes-agent")
    except Exception:
        return None


def print_version() -> int:
    project_root = get_project_root()
    vendor_path = get_vendor_hermes_path()

    reins_commit = get_git_commit(project_root)
    reins_branch = get_git_branch(project_root)

    hermes_commit = get_git_commit(vendor_path) if vendor_path.exists() else None
    hermes_branch = get_git_branch(vendor_path) if vendor_path.exists() else None
    hermes_version = get_hermes_version()

    print(f"Reins {__version__}")

    if reins_branch or reins_commit:
        print(f"Reins git: {reins_branch or 'unknown'} {reins_commit or 'unknown'}")

    if hermes_version:
        print(f"Agent runtime: {hermes_version}")

    if hermes_branch or hermes_commit:
        print(f"Core git: {hermes_branch or 'unknown'} {hermes_commit or 'unknown'}")

    return 0
