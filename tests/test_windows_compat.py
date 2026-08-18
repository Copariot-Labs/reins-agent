from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reins.compat import paths, web
from reins.features.office.chat import open_command_for_path


class WindowsCompatTests(unittest.TestCase):
    def test_windows_desktop_installer_does_not_lock_its_install_directory(self) -> None:
        hooks = (
            Path(__file__).resolve().parents[1]
            / "desktop"
            / "src-tauri"
            / "windows"
            / "hooks.nsh"
        ).read_text(encoding="utf-8")
        desktop_runtime = (
            Path(__file__).resolve().parents[1]
            / "desktop"
            / "src-tauri"
            / "src"
            / "lib.rs"
        ).read_text(encoding="utf-8")

        self.assertNotIn("/inheritance:r", hooks)
        self.assertNotIn("/grant:r", hooks)
        self.assertIn("/inheritance:e /reset", hooks)
        self.assertIn("app_local_data_dir()", desktop_runtime)

    def test_windows_runtime_allows_install_into_private_managed_python(self) -> None:
        staging_script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "stage-windows-runtime.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('"--break-system-packages"', staging_script)
        self.assertIn("Private Reins Python runtime verified", staging_script)

    def test_windows_installer_uses_slow_start_safe_health_check(self) -> None:
        installer = (
            Path(__file__).resolve().parents[1]
            / "deploy"
            / "windows"
            / "install.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn("$request.Proxy = $null", installer)
        self.assertIn("$request.Timeout = 10000", installer)
        self.assertIn("Get-ScheduledTaskInfo", installer)

    def test_windows_installer_registers_managed_updater_without_submodules(self) -> None:
        installer = (
            Path(__file__).resolve().parents[1]
            / "deploy"
            / "windows"
            / "install.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('$UpdateTaskName = "Reins Updater"', installer)
        self.assertIn("Register-ScheduledTask -TaskName $UpdateTaskName", installer)
        self.assertNotIn("git submodule", installer.lower())

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

    def test_office_open_command_is_platform_specific(self) -> None:
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
