from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reins.compat import paths, web
from reins.features.artifacts.plugin import open_command_for_path
from reins.features.presentation.engines.utils import get_venv_python


class WindowsCompatTests(unittest.TestCase):
    def test_configured_paths_expand_environment_variables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REINS_TEST_HOME": directory, "REINS_HOME": "$REINS_TEST_HOME/data"}):
                self.assertEqual(paths.get_reins_home(), (Path(directory) / "data").resolve())

    def test_windows_default_homes_use_local_app_data(self) -> None:
        reins_home = Path("C:/Users/Tester/AppData/Local/reins")
        hermes_home = Path("C:/Users/Tester/AppData/Local/hermes")

        def fake_windows_home(name: str) -> Path:
            return reins_home if name == "reins" else hermes_home

        with patch.object(paths.os, "name", "nt"):
            with patch("reins.compat.paths._windows_local_app_home", side_effect=fake_windows_home):
                self.assertEqual(paths.default_reins_home(), reins_home)
                self.assertEqual(paths.default_hermes_home(), hermes_home)

    def test_web_launcher_uses_windows_venv_layout(self) -> None:
        project_root = Path("C:/repo/reins-agent")
        with patch.object(web.os, "name", "nt"):
            self.assertEqual(
                str(web._get_venv_python(project_root)).replace("\\", "/"),
                "C:/repo/reins-agent/.venv/Scripts/python.exe",
            )
            self.assertEqual(web._activation_command(), r".venv\Scripts\Activate.ps1")

    def test_presentation_venv_python_uses_windows_layout(self) -> None:
        venv = Path("C:/repo/reins-agent/external/.venvs/ppt-master")
        with patch("reins.features.presentation.engines.utils.os.name", "nt"):
            self.assertEqual(
                str(get_venv_python(venv)).replace("\\", "/"),
                "C:/repo/reins-agent/external/.venvs/ppt-master/Scripts/python.exe",
            )

    def test_artifact_open_command_is_platform_specific(self) -> None:
        path = "C:/Users/Tester/Desktop/report.docx"
        self.assertEqual(
            open_command_for_path(path, platform="win32"),
            'start "" "C:/Users/Tester/Desktop/report.docx"',
        )
        self.assertEqual(
            open_command_for_path("/Users/tester/Desktop/report.docx", platform="darwin"),
            'open "/Users/tester/Desktop/report.docx"',
        )


if __name__ == "__main__":
    unittest.main()
