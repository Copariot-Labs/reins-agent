from __future__ import annotations

import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from reins.compat import paths, web
from reins.features.office.chat import open_command_for_path


class WindowsCompatTests(unittest.TestCase):
    def test_desktop_development_uses_fast_transpile_only_typescript(self) -> None:
        desktop_runtime = (
            Path(__file__).resolve().parents[1]
            / "desktop"
            / "src-tauri"
            / "src"
            / "lib.rs"
        ).read_text(encoding="utf-8")
        nodemon_config = (
            Path(__file__).resolve().parents[1]
            / "web"
            / "nodemon.json"
        ).read_text(encoding="utf-8")

        self.assertIn("ts-node/register/transpile-only", desktop_runtime)
        self.assertIn("ts-node/register/transpile-only", nodemon_config)

    def test_tagged_windows_build_publishes_release_assets(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "windows-desktop.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("contents: write", workflow)
        self.assertIn('"release", "create"', workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("Reins-Setup-x64.exe.sha256", workflow)
        self.assertIn("startsWith(github.ref, 'refs/tags/desktop-v')", workflow)

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

    def test_windows_desktop_waits_for_local_service_before_showing_login(self) -> None:
        config = (
            Path(__file__).resolve().parents[1]
            / "desktop"
            / "src-tauri"
            / "tauri.conf.json"
        ).read_text(encoding="utf-8")
        desktop_runtime = (
            Path(__file__).resolve().parents[1]
            / "desktop"
            / "src-tauri"
            / "src"
            / "lib.rs"
        ).read_text(encoding="utf-8")

        self.assertIn('"visible": false', config)
        self.assertIn("wait_for_backend(&state, 8648", desktop_runtime)
        self.assertIn("GET /health/ready", desktop_runtime)
        self.assertIn("backend_exit_detail", desktop_runtime)
        self.assertIn("desktop-backend.log", desktop_runtime)
        self.assertIn("window.show()", desktop_runtime)

    def test_windows_desktop_keeps_tauri_download_bridge_after_startup(self) -> None:
        desktop_runtime = (
            Path(__file__).resolve().parents[1]
            / "desktop"
            / "src-tauri"
            / "src"
            / "lib.rs"
        ).read_text(encoding="utf-8")
        download_helper = (
            Path(__file__).resolve().parents[1]
            / "web"
            / "packages"
            / "client"
            / "src"
            / "api"
            / "hermes"
            / "download.ts"
        ).read_text(encoding="utf-8")

        self.assertNotIn("window.navigate(", desktop_runtime)
        self.assertIn('window.eval("window.location.reload()")', desktop_runtime)
        self.assertIn("generate_handler![save_download]", desktop_runtime)
        self.assertIn("invoke<boolean>('save_download'", download_helper)

    def test_windows_desktop_starts_slow_services_after_http_readiness(self) -> None:
        server_entry = (
            Path(__file__).resolve().parents[1]
            / "web"
            / "packages"
            / "server"
            / "src"
            / "index.ts"
        ).read_text(encoding="utf-8")

        listen_position = server_entry.index("await listenWithFallback")
        bridge_position = server_entry.index("void startAgentBridgeManager()")
        product_position = server_entry.index("void initializeProductServices()")
        self.assertLess(listen_position, bridge_position)
        self.assertLess(listen_position, product_position)

    def test_windows_desktop_uses_a_drive_letter_safe_node_entry(self) -> None:
        desktop_runtime = (
            Path(__file__).resolve().parents[1]
            / "desktop"
            / "src-tauri"
            / "src"
            / "lib.rs"
        ).read_text(encoding="utf-8")
        staging_script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "stage-windows-runtime.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('.arg(Path::new("server").join("index.js"))', desktop_runtime)
        self.assertNotIn(".arg(&server)", desktop_runtime)
        self.assertIn('@("--check", "server\\index.js")', staging_script)
        self.assertIn('Start-Process -FilePath $RuntimeNode', staging_script)
        self.assertIn('/health/ready', staging_script)
        self.assertIn('Staged Reins local service verified', staging_script)

    def test_windows_runtime_allows_install_into_private_managed_python(self) -> None:
        staging_script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "stage-windows-runtime.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('"--break-system-packages"', staging_script)
        self.assertIn("Private Reins Python runtime verified", staging_script)

    def test_windows_runtime_builds_and_verifies_native_javascript_dependencies(self) -> None:
        staging_script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "stage-windows-runtime.ps1"
        ).read_text(encoding="utf-8")

        self.assertIn('onlyBuiltDependencies = @("node-pty")', staging_script)
        self.assertIn("Private Reins JavaScript runtime verified", staging_script)

    def test_finance_migrations_are_packaged_and_verified_in_windows_runtime(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        packaging = tomllib.loads(
            (project_root / "pyproject.toml").read_text(encoding="utf-8")
        )
        staging_script = (project_root / "scripts" / "stage-windows-runtime.ps1").read_text(
            encoding="utf-8"
        )

        package_data = packaging["tool"]["setuptools"]["package-data"]
        self.assertIn("migrations/*.sql", package_data["reins.features.finance"])
        self.assertIn("get_migrations_dir", staging_script)
        self.assertIn("required=migrations/'001_init.sql'", staging_script)
        self.assertIn("Finance migrations verified", staging_script)

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
