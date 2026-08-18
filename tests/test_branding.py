from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from reins.compat.branding import (
    REINS_IDENTITY_START,
    ensure_reins_branding,
    merge_reins_identity,
)
from reins.compat.env import prepare_env


class ReinsBrandingTests(unittest.TestCase):
    def test_merge_preserves_custom_instructions_and_updates_managed_block(self) -> None:
        original = "Keep answers concise."
        first = merge_reins_identity(original)
        second = merge_reins_identity(first)

        self.assertEqual(first, second)
        self.assertIn(original, second)
        self.assertIn("You are Reins Agent", second)
        self.assertEqual(second.count(REINS_IDENTITY_START), 1)
        self.assertNotIn("Hermes Agent", second)
        self.assertNotIn("Nous Research", second)

    def test_branding_covers_root_and_existing_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "reins"
            profile = home / "profiles" / "office-team"
            profile.mkdir(parents=True)
            (home / "config.yaml").write_text(
                "agent:\n  system_prompt: Keep the root prompt.\n",
                encoding="utf-8",
            )
            (profile / "config.yaml").write_text(
                "agent:\n  system_prompt: Keep the profile prompt.\n",
                encoding="utf-8",
            )
            (profile / "SOUL.md").write_text(
                "Use a calm, professional tone.\n",
                encoding="utf-8",
            )

            ensure_reins_branding(home)

            for profile_home, custom in (
                (home, "Keep the root prompt."),
                (profile, "Keep the profile prompt."),
            ):
                soul = (profile_home / "SOUL.md").read_text(encoding="utf-8")
                config = yaml.safe_load(
                    (profile_home / "config.yaml").read_text(encoding="utf-8")
                )
                prompt = config["agent"]["system_prompt"]
                self.assertIn("You are Reins Agent", soul)
                self.assertIn("You are Reins Agent", prompt)
                self.assertIn(custom, prompt)

            self.assertIn(
                "Use a calm, professional tone.",
                (profile / "SOUL.md").read_text(encoding="utf-8"),
            )

    def test_prepare_env_brands_without_vendor_specific_identity_variables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REINS_HOME": directory}, clear=True):
                home = prepare_env()
                environment = dict(os.environ)

            self.assertTrue((home / "SOUL.md").is_file())
            self.assertNotIn("HERMES_AGENT_IDENTITY", environment)
            self.assertNotIn("HERMES_AGENT_HELP_GUIDANCE", environment)


if __name__ == "__main__":
    unittest.main()
