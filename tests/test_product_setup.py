from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from reins.product_setup import setup_product


class ProductSetupTests(unittest.TestCase):
    def test_setup_enables_product_features_for_root_and_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "reins"
            profile = home / "profiles" / "office-team"
            profile.mkdir(parents=True)
            (profile / "config.yaml").write_text(
                "plugins:\n  disabled:\n    - reins-finance\n    - reins-wecom\n",
                encoding="utf-8",
            )
            doctor = {
                "ok": False,
                "notification": {
                    "group_webhook_ready": False,
                    "roles": {},
                },
            }

            with patch.dict(
                os.environ,
                {"REINS_HOME": str(home), "HERMES_HOME": str(home)},
                clear=True,
            ):
                with patch(
                    "reins.product_setup.officecli_status",
                    return_value={"available": True},
                ):
                    with patch(
                        "reins.product_setup.ticket_api_doctor",
                        return_value=doctor,
                    ):
                        result = setup_product()

            self.assertTrue(result["finance"]["enabled"])
            self.assertTrue(result["office"]["available"])
            self.assertTrue(result["wecom"]["enabled"])
            for config_path in (home / "config.yaml", profile / "config.yaml"):
                config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                plugins = config["plugins"]
                self.assertEqual(
                    set(plugins["enabled"]),
                    {"reins-finance", "reins-wecom"},
                )
                self.assertEqual(plugins["disabled"], [])
                self.assertFalse(
                    plugins["entries"]["reins-finance"]["allow_tool_override"]
                )
                self.assertFalse(
                    plugins["entries"]["reins-wecom"]["allow_tool_override"]
                )
                self.assertIn(
                    "You are Reins Agent",
                    config["agent"]["system_prompt"],
                )
                self.assertIn(
                    "You are Reins Agent",
                    (config_path.parent / "SOUL.md").read_text(encoding="utf-8"),
                )
                self.assertTrue((config_path.parent / "plugins" / "reins-finance").is_dir())
                self.assertTrue((config_path.parent / "plugins" / "reins-wecom").is_dir())


if __name__ == "__main__":
    unittest.main()
