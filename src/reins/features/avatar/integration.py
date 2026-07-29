from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from reins.api.home import get_reins_home
from reins.compat.bootstrap import get_project_root


PLUGIN_NAME = "reins-avatar"
PLUGIN_VERSION = "0.1.0"


@dataclass(frozen=True)
class AvatarStatus:
    reins_home: str
    project_root: str
    companion_source: str
    companion_source_exists: bool
    companion_package_exists: bool
    runtime_python: str
    runtime_python_exists: bool
    launcher_path: str
    launcher_exists: bool
    launcher_executable: bool
    hermes_acp_adapter_available: bool
    npm_available: bool
    node_modules_installed: bool
    message: str

    @property
    def bridge_ready(self) -> bool:
        return (
            self.runtime_python_exists
            and self.launcher_exists
            and self.launcher_executable
            and self.hermes_acp_adapter_available
        )

    @property
    def development_ready(self) -> bool:
        return (
            self.bridge_ready
            and self.companion_source_exists
            and self.companion_package_exists
            and self.npm_available
            and self.node_modules_installed
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bridge_ready"] = self.bridge_ready
        payload["development_ready"] = self.development_ready
        return payload


def get_companion_source_dir() -> Path:
    """
    Return the vendored Reins Agent Companion source directory.
    """

    return get_project_root() / "external" / "avatar"


def get_avatar_plugin_dir() -> Path:
    """
    Return the generated runtime plugin directory.

    macOS/Linux:
        ~/.reins/plugins/reins-avatar

    Windows:
        %LOCALAPPDATA%\\reins\\plugins\\reins-avatar
    """

    return get_reins_home() / "plugins" / PLUGIN_NAME


def get_avatar_bin_dir() -> Path:
    return get_avatar_plugin_dir() / "bin"


def get_avatar_manifest_path() -> Path:
    return get_avatar_plugin_dir() / "integration.json"


def get_runtime_python() -> Path:
    """
    Resolve the Python executable that should run Reins ACP.

    Preserve the virtual-environment executable path. Do not call
    Path.resolve() here because uv virtual environments commonly use
    symlinks. Resolving the symlink would point the launcher at the base
    uv-managed Python installation instead of the Reins virtual environment.
    """

    project_root = get_project_root()

    if os.name == "nt":
        project_python = (
            project_root
            / ".venv"
            / "Scripts"
            / "python.exe"
        )
    else:
        project_python = (
            project_root
            / ".venv"
            / "bin"
            / "python"
        )

    if project_python.is_file():
        return project_python.absolute()

    return Path(sys.executable).absolute()

def get_avatar_launcher_path() -> Path:
    """
    Return the platform-specific generated ACP launcher path.
    """

    if os.name == "nt":
        return get_avatar_bin_dir() / "reins-avatar-acp.cmd"

    return get_avatar_bin_dir() / "reins-avatar-acp"


def build_companion_config(
    launcher_path: Path | None = None,
) -> dict[str, Any]:
    """
    Return the connection details used by Reins Agent Companion.
    """

    launcher = launcher_path or get_avatar_launcher_path()

    return {
        "name": "Reins Agent",
        "preset": "reins",
        "protocol": "acp",
        "transport": "stdio",
        "program": str(launcher.resolve()),
        "args": [],
        "reins_home": str(get_reins_home().resolve()),
        "companion_source": str(
            get_companion_source_dir().resolve()
        ),
    }


def _write_posix_launcher(
    launcher_path: Path,
    python_path: Path,
) -> None:
    quoted_python = shlex.quote(str(python_path))

    content = "\n".join(
        [
            "#!/usr/bin/env sh",
            "set -eu",
            "",
            "# Reins Agent Companion ACP bridge.",
            "# Standard output is reserved for ACP JSON-RPC.",
            "export PYTHONUTF8=1",
            "",
            (
                f'exec {quoted_python} '
                '-m reins.main acp "$@"'
            ),
            "",
        ]
    )

    launcher_path.write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )

    current_mode = launcher_path.stat().st_mode

    launcher_path.chmod(
        current_mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )


def _write_windows_launcher(
    launcher_path: Path,
    python_path: Path,
) -> None:
    content = "\r\n".join(
        [
            "@echo off",
            "setlocal",
            "set PYTHONUTF8=1",
            "",
            "rem Reins Agent Companion ACP bridge.",
            "rem Standard output is reserved for ACP JSON-RPC.",
            (
                f'"{python_path}" '
                "-m reins.main acp %*"
            ),
            "",
        ]
    )

    launcher_path.write_text(
        content,
        encoding="utf-8",
        newline="",
    )


def _write_manifest(launcher_path: Path) -> Path:
    manifest_path = get_avatar_manifest_path()

    payload = {
        "name": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "description": (
            "ACP bridge connecting Reins Agent Companion "
            "to Reins and Hermes."
        ),
        "companion": build_companion_config(
            launcher_path
        ),
    }

    manifest_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return manifest_path


def install_avatar_bridge() -> Path:
    """
    Generate a stable ACP launcher under REINS_HOME.

    The companion application starts this launcher instead of depending on
    the terminal PATH or a manually activated virtual environment.
    """

    python_path = get_runtime_python()

    if not python_path.is_file():
        raise RuntimeError(
            "Reins Python executable was not found: "
            f"{python_path}"
        )

    plugin_dir = get_avatar_plugin_dir()
    bin_dir = get_avatar_bin_dir()
    launcher_path = get_avatar_launcher_path()

    plugin_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    bin_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if os.name == "nt":
        _write_windows_launcher(
            launcher_path,
            python_path,
        )
    else:
        _write_posix_launcher(
            launcher_path,
            python_path,
        )

    _write_manifest(launcher_path)

    return launcher_path


def uninstall_avatar_bridge() -> bool:
    """
    Remove generated runtime bridge files.

    This does not delete the companion source code or companion user data.
    """

    plugin_dir = get_avatar_plugin_dir()

    if not plugin_dir.exists():
        return False

    shutil.rmtree(plugin_dir)

    return True


def _is_launcher_executable(path: Path) -> bool:
    if not path.is_file():
        return False

    if os.name == "nt":
        return True

    return os.access(path, os.X_OK)


def _hermes_acp_adapter_available() -> bool:
    """
    Check that the Hermes ACP adapter can be imported.

    This avoids starting the actual ACP stdio server during a doctor check.
    """

    try:
        return (
            importlib.util.find_spec(
                "acp_adapter"
            )
            is not None
        )
    except (
        ImportError,
        ModuleNotFoundError,
        ValueError,
    ):
        return False


def _find_npm() -> str | None:
    candidates = (
        ["npm.cmd", "npm"]
        if os.name == "nt"
        else ["npm"]
    )

    for candidate in candidates:
        resolved = shutil.which(candidate)

        if resolved:
            return resolved

    return None


def get_avatar_status() -> AvatarStatus:
    companion_source = get_companion_source_dir()
    package_json = companion_source / "package.json"
    node_modules = companion_source / "node_modules"

    runtime_python = get_runtime_python()
    launcher_path = get_avatar_launcher_path()

    hermes_acp_available = (
        _hermes_acp_adapter_available()
    )

    npm_available = _find_npm() is not None

    if not companion_source.is_dir():
        message = (
            "Reins Agent Companion source was not found at "
            f"{companion_source}."
        )
    elif not package_json.is_file():
        message = (
            "The companion package.json file was not found."
        )
    elif not runtime_python.is_file():
        message = (
            "The Reins virtual-environment Python "
            "executable was not found."
        )
    elif not hermes_acp_available:
        message = (
            "Hermes ACP support is unavailable. Install Hermes "
            "with its ACP optional dependencies."
        )
    elif not launcher_path.is_file():
        message = (
            "The avatar bridge is not installed. Run "
            "`reins avatar install`."
        )
    elif not _is_launcher_executable(
        launcher_path
    ):
        message = (
            "The avatar bridge exists but is not executable. "
            "Run `reins avatar install` again."
        )
    elif not npm_available:
        message = (
            "npm was not found. Install Node.js and npm."
        )
    elif not node_modules.is_dir():
        message = (
            "The avatar bridge is ready. Companion frontend "
            "dependencies are not installed yet."
        )
    else:
        message = (
            "Reins Agent Companion development environment "
            "is ready."
        )

    return AvatarStatus(
        reins_home=str(
            get_reins_home().resolve()
        ),
        project_root=str(
            get_project_root().resolve()
        ),
        companion_source=str(
            companion_source.resolve()
        ),
        companion_source_exists=(
            companion_source.is_dir()
        ),
        companion_package_exists=(
            package_json.is_file()
        ),
        runtime_python=str(runtime_python),
        runtime_python_exists=(
            runtime_python.is_file()
        ),
        launcher_path=str(
            launcher_path.resolve()
        ),
        launcher_exists=(
            launcher_path.is_file()
        ),
        launcher_executable=(
            _is_launcher_executable(
                launcher_path
            )
        ),
        hermes_acp_adapter_available=(
            hermes_acp_available
        ),
        npm_available=npm_available,
        node_modules_installed=(
            node_modules.is_dir()
        ),
        message=message,
    )


def _run_companion_command(
    command_arguments: Sequence[str],
) -> int:
    companion_source = get_companion_source_dir()

    if not companion_source.is_dir():
        raise RuntimeError(
            "Reins Agent Companion source was not found: "
            f"{companion_source}"
        )

    package_json = companion_source / "package.json"

    if not package_json.is_file():
        raise RuntimeError(
            "Reins Agent Companion package.json was not found: "
            f"{package_json}"
        )

    npm_path = _find_npm()

    if npm_path is None:
        raise RuntimeError(
            "npm was not found. Install Node.js and npm."
        )

    launcher_path = get_avatar_launcher_path()

    if not launcher_path.is_file():
        launcher_path = install_avatar_bridge()

    environment = os.environ.copy()

    environment["REINS_HOME"] = str(
        get_reins_home().resolve()
    )

    environment["REINS_AVATAR_ACP_COMMAND"] = str(
        launcher_path.resolve()
    )

    environment["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [
            npm_path,
            *command_arguments,
        ],
        cwd=companion_source,
        env=environment,
        check=False,
    )

    return int(result.returncode)


def install_companion_dependencies() -> int:
    """
    Install the companion's locked npm dependencies.
    """

    return _run_companion_command(
        ["ci"]
    )


def run_companion_development() -> int:
    """
    Start the complete Tauri desktop application in development mode.
    """

    return _run_companion_command(
        [
            "run",
            "tauri",
            "dev",
        ]
    )


def build_companion_production() -> int:
    """
    Build the platform-specific production companion package.
    """

    return _run_companion_command(
        [
            "run",
            "tauri",
            "build",
        ]
    )