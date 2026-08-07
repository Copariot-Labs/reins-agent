from __future__ import annotations

import os
import subprocess
import sys
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


def _read_installed_project(path: Path) -> Path | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return Path(value).expanduser().resolve() if value else None
    except OSError:
        return None


def _trigger_managed_update(project_root: Path, dry_run: bool) -> bool:
    if sys.platform.startswith("linux"):
        state_dir = Path.home() / ".config" / "reins"
        installed_root = _read_installed_project(state_dir / "project-root")
        unit_path = Path.home() / ".config" / "systemd" / "user" / "reins-update.service"
        if installed_root == project_root.resolve() and unit_path.exists():
            print("Queueing the installed Reins update service...")
            _run(
                ["systemctl", "--user", "start", "--no-block", "reins-update.service"],
                cwd=project_root,
                dry_run=dry_run,
            )
            return True

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            state_dir = Path(local_app_data) / "reins-deploy"
            installed_root = _read_installed_project(state_dir / "project-root")
            updater = state_dir / "reins-update.ps1"
            if installed_root == project_root.resolve() and updater.exists():
                powershell = (
                    Path(os.environ.get("SystemRoot", r"C:\Windows"))
                    / "System32"
                    / "WindowsPowerShell"
                    / "v1.0"
                    / "powershell.exe"
                )
                print("Queueing the installed Reins updater task...")
                _run(
                    [
                        str(powershell),
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        "Start-ScheduledTask -TaskName 'Reins Updater'",
                    ],
                    cwd=project_root,
                    dry_run=dry_run,
                )
                return True

    return False


def update_reins(dry_run: bool = False) -> int:
    project_root = get_project_root()
    vendor_path = get_vendor_hermes_path()

    if not (project_root / ".git").exists():
        raise UpdateError(f"Reins repo is not a git repository: {project_root}")

    if _trigger_managed_update(project_root, dry_run=dry_run):
        print("Reins update started. The application will restart automatically.")
        return 0

    if not vendor_path.exists():
        raise UpdateError(f"Hermes vendor directory not found: {vendor_path}")

    print("Updating Reins repository...")
    _run(["git", "pull", "--ff-only"], cwd=project_root, dry_run=dry_run)

    print("Reinstalling editable packages...")
    _run(["uv", "pip", "install", "--python", str(project_root / ".venv"), "-e", "vendor/hermes-agent"], cwd=project_root, dry_run=dry_run)
    _run(["uv", "pip", "install", "--python", str(project_root / ".venv"), "-e", "."], cwd=project_root, dry_run=dry_run)

    print("Running Reins doctor...")
    _run(["reins", "doctor"], cwd=project_root, dry_run=dry_run)

    print("Reins update complete.")
    return 0
