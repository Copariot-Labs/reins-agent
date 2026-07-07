from __future__ import annotations

from pathlib import Path
import shutil

from reins.api.home import get_reins_home


PLUGIN_NAME = "reins-wechat"


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
                "name: reins-wechat",
                'version: "0.1.0"',
                "description: Deterministic Reins WeChat desktop automation tools",
                "kind: standalone",
                "provides_tools:",
                "  - wechat_doctor",
                "  - wechat_open",
                "  - wechat_search_contact",
                "  - wechat_draft_message",
                "  - wechat_send_current_draft",
                "  - wechat_send_message",
                "  - wechat_draft_file",
                "  - wechat_send_file",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_plugin_init(plugin_dir: Path) -> None:
    source_plugin = get_source_plugin_file()
    target_plugin = plugin_dir / "reins_wechat_plugin.py"
    target_init = plugin_dir / "__init__.py"

    shutil.copy2(source_plugin, target_plugin)

    target_init.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "from .reins_wechat_plugin import register",
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
    print("Reins WeChat Hermes plugin installed.")
    print(f"Plugin directory: {plugin_dir}")
    print()
    print("Enable it with:")
    print("  reins plugins enable reins-wechat")
    print()
    print("Then restart chat and ask for WeChat drafting/sending from the Web UI.")
