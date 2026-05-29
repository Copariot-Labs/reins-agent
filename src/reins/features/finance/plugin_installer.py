from __future__ import annotations

import shutil
from pathlib import Path

from reins.api.home import get_reins_home


PLUGIN_NAME = "reins-finance"


def get_plugins_dir() -> Path:
    return get_reins_home() / "plugins"


def get_plugin_dir() -> Path:
    return get_plugins_dir() / PLUGIN_NAME


def get_source_plugin_file() -> Path:
    return Path(__file__).resolve().parent / "hermes_plugin.py"


def write_plugin_yaml(plugin_dir: Path) -> None:
    plugin_yaml = plugin_dir / "plugin.yaml"
    plugin_yaml.write_text(
        "\n".join(
            [
                "name: reins-finance",
                'version: "0.1.0"',
                "description: Reins local finance tools for Hermes Agent",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_plugin_init(plugin_dir: Path) -> None:
    source_plugin = get_source_plugin_file()
    target_plugin = plugin_dir / "reins_finance_plugin.py"
    target_init = plugin_dir / "__init__.py"

    shutil.copy2(source_plugin, target_plugin)

    target_init.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "from .reins_finance_plugin import register",
                "",
            ]
        ),
        encoding="utf-8",
    )


def install_hermes_plugin() -> Path:
    plugin_dir = get_plugin_dir()
    plugin_dir.mkdir(parents=True, exist_ok=True)

    write_plugin_yaml(plugin_dir)
    write_plugin_init(plugin_dir)

    return plugin_dir


def print_install_instructions(plugin_dir: Path) -> None:
    print("Reins Finance Hermes plugin installed.")
    print(f"Plugin directory: {plugin_dir}")
    print()
    print("Enable it with:")
    print("  reins plugins enable reins-finance")
    print()
    print("Then restart chat:")
    print('  reins chat "帮我记录今天买咖啡 28"')