from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reins.features.avatar.integration import (
    build_companion_config,
    get_avatar_launcher_path,
    get_avatar_manifest_path,
    install_avatar_bridge,
    uninstall_avatar_bridge,
)


class AvatarIntegrationTests(
    unittest.TestCase
):
    def test_install_creates_launcher_and_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                },
                clear=False,
            ):
                with patch(
                    (
                        "reins.features.avatar."
                        "integration.get_runtime_python"
                    ),
                    return_value=Path(
                        sys.executable
                    ),
                ):
                    launcher = (
                        install_avatar_bridge()
                    )

                manifest_path = (
                    get_avatar_manifest_path()
                )

                self.assertTrue(
                    launcher.is_file()
                )

                self.assertTrue(
                    manifest_path.is_file()
                )

                if os.name != "nt":
                    self.assertTrue(
                        os.access(
                            launcher,
                            os.X_OK,
                        )
                    )

                launcher_text = (
                    launcher.read_text(
                        encoding="utf-8"
                    )
                )

                self.assertIn(
                    "-m reins.main acp",
                    launcher_text,
                )

                manifest = json.loads(
                    manifest_path.read_text(
                        encoding="utf-8"
                    )
                )

                self.assertEqual(
                    manifest["name"],
                    "reins-avatar",
                )

                self.assertEqual(
                    manifest[
                        "companion"
                    ]["preset"],
                    "reins",
                )

                self.assertEqual(
                    manifest[
                        "companion"
                    ]["protocol"],
                    "acp",
                )

                self.assertEqual(
                    manifest[
                        "companion"
                    ]["transport"],
                    "stdio",
                )

                self.assertEqual(
                    manifest[
                        "companion"
                    ]["args"],
                    [],
                )

    def test_companion_config_uses_launcher(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                },
                clear=False,
            ):
                config = (
                    build_companion_config()
                )

                self.assertEqual(
                    config["preset"],
                    "reins",
                )

                self.assertEqual(
                    config["protocol"],
                    "acp",
                )

                self.assertEqual(
                    config["transport"],
                    "stdio",
                )

                self.assertEqual(
                    config["args"],
                    [],
                )

                self.assertEqual(
                    Path(
                        config["program"]
                    ),
                    get_avatar_launcher_path().resolve(),
                )

    def test_uninstall_removes_bridge(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                },
                clear=False,
            ):
                with patch(
                    (
                        "reins.features.avatar."
                        "integration.get_runtime_python"
                    ),
                    return_value=Path(
                        sys.executable
                    ),
                ):
                    launcher = (
                        install_avatar_bridge()
                    )

                self.assertTrue(
                    launcher.exists()
                )

                self.assertTrue(
                    uninstall_avatar_bridge()
                )

                self.assertFalse(
                    launcher.exists()
                )

                self.assertFalse(
                    uninstall_avatar_bridge()
                )


if __name__ == "__main__":
    unittest.main()