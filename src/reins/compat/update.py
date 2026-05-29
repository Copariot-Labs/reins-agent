from __future__ import annotations

import subprocess
from pathlib import Path

from reins.compat.bootstrap import get_project_root, get_vendor_hermes_path


class UpdateError(RuntimeError):
    pass


def _run(command: list[str], cwd: Path, dry_run: bool = False) -> None:
    printable = " ".join(command)
    print(f"$ {printable}")

    if dry_run:
        return

    result = subprocess.run(command, cwd=cwd)

    if result.returncode != 0:
        raise UpdateError(f"Command failed with exit code {result.returncode}: {printable}")


def update_reins(dry_run: bool = False) -> int:
    project_root = get_project_root()
    vendor_path = get_vendor_hermes_path()

    if not (project_root / ".git").exists():
        raise UpdateError(f"Reins repo is not a git repository: {project_root}")

    print("Updating Reins repository...")
    _run(["git", "pull"], cwd=project_root, dry_run=dry_run)

    print("Updating Hermes vendor submodule...")
    _run(["git", "submodule", "update", "--init", "--recursive"], cwd=project_root, dry_run=dry_run)

    if vendor_path.exists():
        _run(["git", "fetch", "origin"], cwd=vendor_path, dry_run=dry_run)
    else:
        raise UpdateError(f"Hermes vendor directory not found: {vendor_path}")

    print("Reinstalling editable packages...")
    _run(["uv", "pip", "install", "-e", "vendor/hermes-agent"], cwd=project_root, dry_run=dry_run)
    _run(["uv", "pip", "install", "-e", "."], cwd=project_root, dry_run=dry_run)

    print("Running Reins doctor...")
    _run(["reins", "doctor"], cwd=project_root, dry_run=dry_run)

    print("Reins update complete.")
    return 0