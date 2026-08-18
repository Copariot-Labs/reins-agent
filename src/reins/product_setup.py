from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv
import yaml

from reins.api.home import get_reins_home
from reins.compat.branding import ensure_reins_branding
from reins.features.finance.plugin_installer import install_hermes_plugin as install_finance_plugin
from reins.features.office.officecli_client import officecli_status
from reins.features.office.paths import office_backups_dir, office_documents_dir, office_previews_dir
from reins.features.wecom.plugin_installer import install_hermes_plugin as install_wecom_plugin
from reins.features.wecom.ticket_api import TicketAPIConfig, ticket_api_doctor
from reins.features.wecom.ticket_service import install_service, service_status


PRODUCT_PLUGINS = ("reins-finance", "reins-wecom")


def _config_paths(home: Path) -> list[Path]:
    paths = [home / "config.yaml"]
    profiles = home / "profiles"
    if profiles.is_dir():
        paths.extend(
            profile / "config.yaml"
            for profile in profiles.iterdir()
            if profile.is_dir() and not profile.name.startswith(".")
        )
    return paths


def _enable_product_plugins(config_path: Path) -> None:
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    plugins = payload.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        plugins = {}
        payload["plugins"] = plugins

    enabled = plugins.get("enabled")
    enabled_names = [str(item) for item in enabled] if isinstance(enabled, list) else []
    for name in PRODUCT_PLUGINS:
        if name not in enabled_names:
            enabled_names.append(name)
    plugins["enabled"] = sorted(set(enabled_names))

    disabled = plugins.get("disabled")
    disabled_names = [str(item) for item in disabled] if isinstance(disabled, list) else []
    plugins["disabled"] = sorted(name for name in set(disabled_names) if name not in PRODUCT_PLUGINS)

    entries = plugins.setdefault("entries", {})
    if not isinstance(entries, dict):
        entries = {}
        plugins["entries"] = entries
    for name in PRODUCT_PLUGINS:
        entry = entries.setdefault(name, {})
        if not isinstance(entry, dict):
            entry = {}
            entries[name] = entry
        entry["allow_tool_override"] = False

    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = config_path.with_name(f".{config_path.name}.tmp")
    temporary.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temporary.replace(config_path)


def _load_product_env(home: Path) -> None:
    env_path = home / ".env"
    try:
        load_dotenv(env_path, override=False, encoding="utf-8-sig")
    except UnicodeDecodeError:
        load_dotenv(env_path, override=False, encoding="latin-1")


def _wecom_ready(doctor: dict[str, Any]) -> bool:
    notification = doctor.get("notification")
    if not isinstance(notification, dict) or not notification.get("group_webhook_ready"):
        return False
    roles = notification.get("roles")
    return bool(
        doctor.get("ok")
        and isinstance(roles, dict)
        and roles
        and all(isinstance(role, dict) and role.get("ready") for role in roles.values())
    )


def setup_product(*, enable_background_wecom: bool = False) -> dict[str, Any]:
    home = get_reins_home()
    home.mkdir(parents=True, exist_ok=True)
    for path in (
        home / "logs",
        home / "wecom",
        home / "finance",
        office_documents_dir(),
        office_previews_dir(),
        office_backups_dir(),
    ):
        path.mkdir(parents=True, exist_ok=True)

    finance_plugins = install_finance_plugin()
    wecom_plugins = install_wecom_plugin()
    for config_path in _config_paths(home):
        _enable_product_plugins(config_path)
    ensure_reins_branding(home)

    _load_product_env(home)
    wecom_doctor = ticket_api_doctor(TicketAPIConfig.from_env())
    wecom_ready = _wecom_ready(wecom_doctor)
    background: dict[str, Any] | None = None
    if enable_background_wecom:
        background = install_service() if wecom_ready else service_status()

    return {
        "ok": True,
        "product": "Reins",
        "home": str(home),
        "finance": {
            "enabled": True,
            "plugins": [str(path) for path in finance_plugins],
        },
        "office": officecli_status(),
        "wecom": {
            "enabled": True,
            "configured": wecom_ready,
            "plugins": [str(path) for path in wecom_plugins],
            "doctor": wecom_doctor,
            "background": background,
        },
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv or [])
    enable_background = "--enable-background-wecom" in arguments
    result = setup_product(enable_background_wecom=enable_background)
    if "--json" in arguments:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Reins is ready.")
        print(f"Data: {result['home']}")
        print(f"Finance: {'ready' if result['finance']['enabled'] else 'unavailable'}")
        print(f"Office: {'ready' if result['office'].get('available') else 'needs runtime'}")
        print(f"WeCom: {'ready' if result['wecom']['configured'] else 'needs configuration'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
