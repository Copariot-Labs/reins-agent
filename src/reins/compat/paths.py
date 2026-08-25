from __future__ import annotations

import os
from pathlib import Path


REINS_WORKSPACE_FOLDERS = (
    "Inbox",
    "Word",
    "Excel",
    "PowerPoint",
    "Generated",
    "Projects",
)


def _configured_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser().resolve()


def _windows_local_app_home(name: str) -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")

    if not local_app_data:
        return None

    return Path(local_app_data) / name


def default_reins_home() -> Path:
    if os.name == "nt":
        return _windows_local_app_home("reins") or (Path.home() / ".reins")

    return Path.home() / ".reins"


def default_hermes_home() -> Path:
    if os.name == "nt":
        return _windows_local_app_home("hermes") or (Path.home() / ".hermes")

    return Path.home() / ".hermes"


def default_reins_workspace() -> Path:
    return Path.home() / "Documents" / "Reins Workspace"


def get_reins_home() -> Path:
    value = os.environ.get("REINS_HOME")

    if value:
        return _configured_path(value)

    return default_reins_home().resolve()


def get_hermes_home() -> Path:
    value = os.environ.get("HERMES_HOME")

    if value:
        return _configured_path(value)

    return default_hermes_home().resolve()


def get_reins_workspace() -> Path:
    value = os.environ.get("REINS_WORKSPACE_ROOT")

    if value:
        return _configured_path(value)

    return default_reins_workspace().resolve()


def ensure_reins_home() -> Path:
    reins_home = get_reins_home()
    reins_home.mkdir(parents=True, exist_ok=True)
    return reins_home


def ensure_reins_workspace() -> Path:
    workspace = get_reins_workspace()
    workspace.mkdir(parents=True, exist_ok=True)
    for name in REINS_WORKSPACE_FOLDERS:
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return workspace


def reins_workspace_dir(name: str) -> Path:
    if name not in REINS_WORKSPACE_FOLDERS:
        raise ValueError(f"Unknown Reins workspace folder: {name}")
    return ensure_reins_workspace() / name


def migration_marker_path(reins_home: Path | None = None) -> Path:
    if reins_home is None:
        reins_home = get_reins_home()

    return reins_home / ".migrated-from-hermes"
