from __future__ import annotations

from pathlib import Path
import tempfile

import yaml


REINS_IDENTITY_START = "<!-- REINS MANAGED IDENTITY START -->"
REINS_IDENTITY_END = "<!-- REINS MANAGED IDENTITY END -->"

REINS_AGENT_IDENTITY = """# Reins Agent

You are Reins Agent, the AI work assistant inside the Reins application.
When asked who you are, identify yourself simply as Reins Agent and describe
only the user-facing capabilities available in Reins. Never identify yourself
as an underlying model, framework, runtime, vendor, upstream project, or
research organization. Do not expose private implementation details.
"""


def _managed_identity_block() -> str:
    return (
        f"{REINS_IDENTITY_START}\n"
        f"{REINS_AGENT_IDENTITY.strip()}\n"
        f"{REINS_IDENTITY_END}"
    )


def _without_managed_identity(value: str) -> str:
    remaining = value
    while True:
        start = remaining.find(REINS_IDENTITY_START)
        if start < 0:
            break
        end = remaining.find(REINS_IDENTITY_END, start)
        if end < 0:
            break
        remaining = (
            remaining[:start]
            + remaining[end + len(REINS_IDENTITY_END) :]
        )
    return remaining.strip()


def merge_reins_identity(value: str | None) -> str:
    """Append the current Reins identity while preserving user instructions."""
    custom = _without_managed_identity(str(value or ""))
    parts = [custom, _managed_identity_block()] if custom else [_managed_identity_block()]
    return "\n\n".join(parts).strip() + "\n"


def _write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    temporary.replace(path)


def ensure_reins_profile_branding(profile_home: Path) -> list[Path]:
    """Install Reins identity through public runtime configuration files."""
    profile_home.mkdir(parents=True, exist_ok=True)
    updated_paths: list[Path] = []

    soul_path = profile_home / "SOUL.md"
    try:
        current_soul = soul_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current_soul = ""
    branded_soul = merge_reins_identity(current_soul)
    if branded_soul != current_soul:
        _write_text_atomic(soul_path, branded_soul)
        updated_paths.append(soul_path)

    config_path = profile_home / "config.yaml"
    if config_path.is_file():
        try:
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return updated_paths
        if not isinstance(payload, dict):
            return updated_paths

        agent = payload.setdefault("agent", {})
        if not isinstance(agent, dict):
            agent = {}
            payload["agent"] = agent
        current_prompt = str(agent.get("system_prompt", "") or "")
        branded_prompt = merge_reins_identity(current_prompt).strip()
        if branded_prompt != current_prompt:
            agent["system_prompt"] = branded_prompt
            _write_text_atomic(
                config_path,
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            )
            updated_paths.append(config_path)

    return updated_paths


def _profile_homes(home: Path) -> list[Path]:
    result = [home]
    profiles = home / "profiles"
    if profiles.is_dir():
        result.extend(
            path
            for path in sorted(profiles.iterdir())
            if path.is_dir() and not path.name.startswith(".")
        )
    return result


def ensure_reins_branding(home: Path) -> list[Path]:
    updated: list[Path] = []
    for profile_home in _profile_homes(home):
        updated.extend(ensure_reins_profile_branding(profile_home))
    return updated
