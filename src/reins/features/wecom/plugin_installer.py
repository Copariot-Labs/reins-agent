from __future__ import annotations

import shutil
from pathlib import Path

from reins.api.home import get_reins_home
from reins.compat.paths import get_hermes_home


PLUGIN_NAME = "reins-wecom"


def get_source_plugin_file() -> Path:
    return Path(__file__).resolve().parent / "hermes_plugin.py"


def _plugin_homes() -> list[Path]:
    homes = [get_reins_home(), get_hermes_home()]
    hermes_profiles = get_hermes_home() / "profiles"
    if hermes_profiles.is_dir():
        homes.extend(path for path in hermes_profiles.iterdir() if path.is_dir() and not path.name.startswith("."))
    return list(dict.fromkeys(path.resolve() for path in homes))


def _write_plugin(plugin_dir: Path) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(get_source_plugin_file(), plugin_dir / "reins_wecom_plugin.py")
    (plugin_dir / "__init__.py").write_text(
        "from __future__ import annotations\n\nfrom .reins_wecom_plugin import register\n",
        encoding="utf-8",
    )
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: reins-wecom",
                'version: "0.1.0"',
                "description: Reins WeCom group work-order processing tools",
                "kind: standalone",
                "provides_tools:",
                "  - wecom_ingest_group_ticket",
                "  - wecom_record_staff_reply",
                "  - wecom_list_work_orders",
                "  - wecom_get_work_order",
                "  - wecom_work_order_report",
                "  - wecom_export_work_orders_excel",
                "  - wecom_work_order_doctor",
                "",
            ]
        ),
        encoding="utf-8",
    )


def install_hermes_plugin() -> list[Path]:
    plugin_dirs = [home / "plugins" / PLUGIN_NAME for home in _plugin_homes()]
    for plugin_dir in plugin_dirs:
        _write_plugin(plugin_dir)
    return plugin_dirs


def print_install_instructions(plugin_dirs: list[Path]) -> None:
    print("Reins WeCom integration installed.")
    for plugin_dir in plugin_dirs:
        print(f"Plugin directory: {plugin_dir}")
    print()
    print("Enable it for the Reins profile used by the WeCom gateway:")
    print("  reins plugins enable reins-wecom")
    print()
    print("Then restart the Web UI or its managed WeCom gateway.")
