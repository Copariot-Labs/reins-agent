from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from reins.compat.bootstrap import get_project_root
from reins.compat.env import prepare_env


def _get_web_root() -> Path:
    return get_project_root() / "web"


def _get_venv_python(project_root: Path) -> Path:
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "python.exe"

    return project_root / ".venv" / "bin" / "python"


def _activation_command() -> str:
    if os.name == "nt":
        return r".venv\Scripts\Activate.ps1"

    return "source .venv/bin/activate"


def _find_npm_bin() -> str | None:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]

    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path

    return None


def _find_reins_bin() -> str | None:
    return shutil.which("reins")


def run_web(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = []

    reins_home = prepare_env()
    project_root = get_project_root()
    web_root = _get_web_root()
    hermes_agent_root = project_root / "vendor" / "hermes-agent"
    configured_bridge_python = os.environ.get("HERMES_AGENT_BRIDGE_PYTHON")
    bridge_python = (
        Path(os.path.expandvars(configured_bridge_python)).expanduser().resolve()
        if configured_bridge_python
        else _get_venv_python(project_root)
    )

    if not web_root.exists():
        print(f"Web UI directory not found: {web_root}")
        print("Expected Web UI source at: web/")
        return 1

    if not (web_root / "package.json").exists():
        print(f"Web UI package.json not found: {web_root / 'package.json'}")
        print("Make sure the Web UI source is copied into web/.")
        return 1

    if not hermes_agent_root.exists():
        print(f"Reins agent runtime directory not found: {hermes_agent_root}")
        print("The repository checkout is incomplete; clone or update Reins again.")
        return 1

    if not (hermes_agent_root / "run_agent.py").exists():
        print(f"Reins agent runtime entry point not found: {hermes_agent_root / 'run_agent.py'}")
        print("Your Reins runtime checkout may be incomplete.")
        return 1

    reins_bin = _find_reins_bin()
    npm_bin = _find_npm_bin()

    if reins_bin is None:
        print("Could not find `reins` on PATH.")
        print("Activate your virtual environment and reinstall Reins:")
        print(f"  {_activation_command()}")
        print("  uv pip install -e .")
        return 1

    if npm_bin is None:
        print("Could not find `npm` on PATH.")
        print("Install Node.js 23+ and npm, then run:")
        print("  cd web")
        print("  npm install")
        return 1

    if not bridge_python.exists():
        print(f"Bridge Python not found: {bridge_python}")
        print("Create the virtual environment and install Reins:")
        print("  uv venv")
        print(f"  {_activation_command()}")
        print("  uv pip install -e vendor/hermes-agent")
        print("  uv pip install -e .")
        print()
        print(f"Current Python: {sys.executable}")
        return 1

    env = os.environ.copy()
    env["REINS_HOME"] = str(reins_home)
    env["REINS_BIN"] = reins_bin
    env["HERMES_HOME"] = str(reins_home)
    env["HERMES_BIN"] = reins_bin
    env["HERMES_WEB_UI_HOME"] = str(reins_home / "web-ui")
    env["HERMES_AGENT_ROOT"] = str(hermes_agent_root)
    env["HERMES_AGENT_BRIDGE_PYTHON"] = str(bridge_python)

    command = [npm_bin, "run", "dev"]

    if argv and argv[0] == "start":
        command = [npm_bin, "run", "start"]

    print("Starting Reins Web UI")
    print(f"Project root:                 {project_root}")
    print(f"Web root:                     {web_root}")
    print(f"REINS_HOME:                   {env['REINS_HOME']}")
    print(f"REINS_BIN:                    {env['REINS_BIN']}")
    print(f"npm:                          {npm_bin}")
    print(f"HERMES_HOME:                  {env['HERMES_HOME']}")
    print(f"HERMES_BIN:                   {env['HERMES_BIN']}")
    print(f"HERMES_WEB_UI_HOME:           {env['HERMES_WEB_UI_HOME']}")
    print(f"HERMES_AGENT_ROOT:            {env['HERMES_AGENT_ROOT']}")
    print(f"HERMES_AGENT_BRIDGE_PYTHON:   {env['HERMES_AGENT_BRIDGE_PYTHON']}")
    print()

    result = subprocess.run(command, cwd=web_root, env=env)
    return result.returncode
