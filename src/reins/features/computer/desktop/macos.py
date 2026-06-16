from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess

from reins.api.home import get_reins_home
from reins.features.computer.desktop.base import DesktopBackend


class MacOSDesktopBackend(DesktopBackend):
    def _screenshot_dir(self) -> Path:
        path = get_reins_home() / "computer" / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def doctor(self) -> dict:
        return {
            "ok": True,
            "os": "macos",
            "backend": "open / osascript / screencapture",
            "required_permissions": [
                "Accessibility",
                "Screen Recording",
                "Automation",
            ],
        }

    def open_url(self, url: str, app: str | None = None) -> dict:
        cmd = ["open"]

        if app:
            cmd.extend(["-a", app])

        cmd.append(url)
        subprocess.run(cmd, check=True)

        return {
            "ok": True,
            "action": "open_url",
            "url": url,
            "app": app or "default",
        }

    def open_file(self, path: str, app: str | None = None) -> dict:
        file_path = Path(path).expanduser().resolve()

        if not file_path.exists():
            return {
                "ok": False,
                "error": f"File not found: {file_path}",
            }

        cmd = ["open"]

        if app:
            cmd.extend(["-a", app])

        cmd.append(str(file_path))
        subprocess.run(cmd, check=True)

        return {
            "ok": True,
            "action": "open_file",
            "path": str(file_path),
            "app": app or "default",
        }

    def screenshot(self) -> dict:
        out = self._screenshot_dir() / f"screenshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"

        subprocess.run(
            ["screencapture", "-x", str(out)],
            check=True,
        )

        return {
            "ok": True,
            "action": "screenshot",
            "path": str(out),
        }

    def activate_app(self, app_name: str) -> dict:
        script = f'tell application "{app_name}" to activate'

        subprocess.run(
            ["osascript", "-e", script],
            check=True,
        )

        return {
            "ok": True,
            "action": "activate_app",
            "app": app_name,
        }

    def type_text(self, text: str) -> dict:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')

        script = f'''
        tell application "System Events"
            keystroke "{escaped}"
        end tell
        '''

        subprocess.run(
            ["osascript", "-e", script],
            check=True,
        )

        return {
            "ok": True,
            "action": "type_text",
        }

    def hotkey(self, *keys: str) -> dict:
        if len(keys) < 2:
            return {
                "ok": False,
                "error": "hotkey requires at least one modifier and one key",
            }

        key = keys[-1]
        modifiers = ", ".join(keys[:-1])

        script = f'''
        tell application "System Events"
            keystroke "{key}" using {{{modifiers}}}
        end tell
        '''

        subprocess.run(
            ["osascript", "-e", script],
            check=True,
        )

        return {
            "ok": True,
            "action": "hotkey",
            "keys": list(keys),
        }