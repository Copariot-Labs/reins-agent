from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import platform
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

from reins.features.workmode.proof import capture_desktop_screenshot


@dataclass(frozen=True)
class DesktopRect:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class DesktopWindow:
    id: str | None
    title: str
    app: str | None = None
    platform: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _platform_name() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return system or "unknown"


def _run(
    command: list[str],
    *,
    timeout: float = 10,
    input_text: str | None = None,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "status": "missing",
            "command": command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "command": command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    return {
        "ok": completed.returncode == 0,
        "status": "ok" if completed.returncode == 0 else "failed",
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _spawn(command: list[str]) -> dict[str, Any]:
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {
            "ok": True,
            "status": "ok",
            "command": command,
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "status": "missing",
            "command": command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "command": command,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def _osascript(script: str, *, timeout: float = 10) -> dict[str, Any]:
    return _run(["osascript", "-e", script], timeout=timeout)


def _powershell(script: str, *, timeout: float = 10) -> dict[str, Any]:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if not executable:
        return {
            "ok": False,
            "status": "missing",
            "tool": "powershell",
            "error": "PowerShell is not available.",
        }
    return _run([executable, "-NoProfile", "-Command", script], timeout=timeout)


def _powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def parse_rect(value: Any) -> DesktopRect | None:
    if value is None or value == "":
        return None
    if isinstance(value, DesktopRect):
        return value
    if isinstance(value, dict):
        try:
            return DesktopRect(
                x=int(value.get("x", 0)),
                y=int(value.get("y", 0)),
                width=int(value.get("width", value.get("w", 0))),
                height=int(value.get("height", value.get("h", 0))),
            )
        except (TypeError, ValueError):
            return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return DesktopRect(int(value[0]), int(value[1]), int(value[2]), int(value[3]))
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("x", ",").split(",") if part.strip()]
        if len(parts) == 4:
            try:
                return DesktopRect(*(int(part) for part in parts))
            except ValueError:
                return None
    return None


def _screenshot_path(action: dict[str, Any]) -> str | None:
    screenshot = action.get("screenshot")
    if isinstance(screenshot, dict) and screenshot.get("ok") and screenshot.get("path"):
        return str(screenshot["path"])
    return None


class DesktopWindowLayer:
    def __init__(self, *, case_id: str, visible: bool = True, hold_seconds: float = 0.6):
        self.case_id = case_id
        self.visible = visible
        self.hold_seconds = max(0.0, hold_seconds)
        self.platform = _platform_name()

    def capabilities(self) -> dict[str, Any]:
        tools = {
            "open": shutil.which("open") is not None,
            "osascript": shutil.which("osascript") is not None,
            "wmctrl": shutil.which("wmctrl") is not None,
            "xdotool": shutil.which("xdotool") is not None,
            "xdg-open": shutil.which("xdg-open") is not None,
            "powershell": shutil.which("powershell") is not None or shutil.which("pwsh") is not None,
            "screencapture": shutil.which("screencapture") is not None,
            "gnome-screenshot": shutil.which("gnome-screenshot") is not None,
            "imagemagick-import": shutil.which("import") is not None,
        }
        return {
            "ok": True,
            "kind": "desktop_capabilities",
            "platform": self.platform,
            "visible": self.visible,
            "tools": tools,
            "can_open_app": self.platform in {"macos", "linux", "windows"},
            "can_list_windows": (
                (self.platform == "macos" and tools["osascript"])
                or (self.platform == "linux" and tools["wmctrl"])
                or (self.platform == "windows" and tools["powershell"])
            ),
            "can_activate_window": (
                (self.platform == "macos" and tools["osascript"])
                or (self.platform == "linux" and (tools["wmctrl"] or tools["xdotool"]))
                or (self.platform == "windows" and tools["powershell"])
            ),
            "can_move_window": (
                (self.platform == "macos" and tools["osascript"])
                or (self.platform == "linux" and (tools["wmctrl"] or tools["xdotool"]))
                or (self.platform == "windows" and tools["powershell"])
            ),
            "can_screenshot": (
                (self.platform == "macos" and tools["screencapture"])
                or (self.platform == "linux" and (tools["gnome-screenshot"] or tools["imagemagick-import"]))
                or self.platform == "windows"
            ),
        }

    def screen_rect(self) -> dict[str, Any]:
        if self.platform == "macos":
            script = 'tell application "Finder" to get bounds of window of desktop'
            result = _osascript(script)
            if result.get("ok"):
                parts = [part.strip() for part in str(result.get("stdout") or "").split(",")]
                if len(parts) == 4:
                    try:
                        left, top, right, bottom = (int(float(part)) for part in parts)
                        return {
                            "ok": True,
                            "kind": "desktop_screen_rect",
                            "platform": self.platform,
                            "rect": DesktopRect(left, top, right - left, bottom - top).to_dict(),
                        }
                    except ValueError:
                        pass
            return {**result, "kind": "desktop_screen_rect", "platform": self.platform}

        if self.platform == "linux" and shutil.which("xdotool"):
            result = _run(["xdotool", "getdisplaygeometry"])
            if result.get("ok"):
                parts = str(result.get("stdout") or "").split()
                if len(parts) >= 2:
                    try:
                        return {
                            "ok": True,
                            "kind": "desktop_screen_rect",
                            "platform": self.platform,
                            "rect": DesktopRect(0, 0, int(parts[0]), int(parts[1])).to_dict(),
                        }
                    except ValueError:
                        pass
            return {**result, "kind": "desktop_screen_rect", "platform": self.platform}

        if self.platform == "windows":
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$r=[System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea; "
                "Write-Output ($r.X.ToString()+','+$r.Y.ToString()+','+$r.Width.ToString()+','+$r.Height.ToString())"
            )
            result = _powershell(script)
            if result.get("ok"):
                parts = [part.strip() for part in str(result.get("stdout") or "").split(",")]
                if len(parts) == 4:
                    try:
                        return {
                            "ok": True,
                            "kind": "desktop_screen_rect",
                            "platform": self.platform,
                            "rect": DesktopRect(*(int(part) for part in parts)).to_dict(),
                        }
                    except ValueError:
                        pass
            return {**result, "kind": "desktop_screen_rect", "platform": self.platform}

        return {
            "ok": False,
            "kind": "desktop_screen_rect",
            "platform": self.platform,
            "error": "Screen geometry is not supported on this platform.",
        }

    def default_stage_rect(self, role: str = "default") -> DesktopRect | None:
        env_rect = parse_rect(os.getenv("WORKMODE_DESKTOP_RECT", ""))
        if env_rect:
            return env_rect

        screen = self.screen_rect()
        rect = parse_rect(screen.get("rect"))
        if not rect:
            return None

        if role in {"browser", "office", "document", "source"}:
            left = int(rect.width * 0.42)
            return DesktopRect(rect.x + left, rect.y, max(760, rect.width - left), rect.height)

        width = max(900, int(rect.width * 0.72))
        height = max(640, int(rect.height * 0.78))
        x = rect.x + max(0, (rect.width - width) // 2)
        y = rect.y + max(0, (rect.height - height) // 2)
        return DesktopRect(x, y, min(width, rect.width), min(height, rect.height))

    def with_proof(self, action: dict[str, Any], *, label: str) -> dict[str, Any]:
        if not self.visible:
            return action
        if self.hold_seconds > 0:
            time.sleep(self.hold_seconds)
        screenshot = capture_desktop_screenshot(case_id=self.case_id, label=label)
        action["screenshot"] = screenshot
        if screenshot.get("ok") and screenshot.get("path"):
            action["screenshot_path"] = str(screenshot["path"])
        return action

    def active_window(self) -> dict[str, Any]:
        if self.platform == "macos":
            script = """
tell application "System Events"
  set frontApp to first application process whose frontmost is true
  set appName to name of frontApp
  set winName to ""
  try
    set winName to name of front window of frontApp
  end try
  return appName & tab & winName
end tell
""".strip()
            result = _osascript(script)
            if result.get("ok"):
                app, _, title = str(result.get("stdout") or "").partition("\t")
                return {
                    "ok": True,
                    "kind": "desktop_active_window",
                    "platform": self.platform,
                    "window": DesktopWindow(id=None, app=app.strip(), title=title.strip(), platform=self.platform).to_dict(),
                }
            return {**result, "kind": "desktop_active_window", "platform": self.platform}

        if self.platform == "linux" and shutil.which("xdotool"):
            result = _run(["xdotool", "getactivewindow", "getwindowname"])
            id_result = _run(["xdotool", "getactivewindow"])
            if result.get("ok"):
                return {
                    "ok": True,
                    "kind": "desktop_active_window",
                    "platform": self.platform,
                    "window": DesktopWindow(
                        id=str(id_result.get("stdout") or "").strip() if id_result.get("ok") else None,
                        title=str(result.get("stdout") or "").strip(),
                        platform=self.platform,
                    ).to_dict(),
                }
            return {**result, "kind": "desktop_active_window", "platform": self.platform}

        if self.platform == "windows":
            script = (
                "$p=Get-Process | Where-Object {$_.MainWindowHandle -ne 0} | "
                "Sort-Object StartTime -Descending | Select-Object -First 1; "
                "if ($p) { Write-Output ($p.Id.ToString()+\"`t\"+$p.ProcessName+\"`t\"+$p.MainWindowTitle) }"
            )
            result = _powershell(script)
            if result.get("ok") and result.get("stdout"):
                window_id, _, rest = str(result["stdout"]).partition("\t")
                app, _, title = rest.partition("\t")
                return {
                    "ok": True,
                    "kind": "desktop_active_window",
                    "platform": self.platform,
                    "window": DesktopWindow(id=window_id.strip(), app=app.strip(), title=title.strip(), platform=self.platform).to_dict(),
                }
            return {**result, "kind": "desktop_active_window", "platform": self.platform}

        return {
            "ok": False,
            "kind": "desktop_active_window",
            "platform": self.platform,
            "error": "Active window lookup is not supported on this platform.",
        }

    def list_windows(self) -> dict[str, Any]:
        if self.platform == "macos":
            script = """
set output to ""
tell application "System Events"
  repeat with proc in application processes
    if visible of proc is true then
      repeat with win in windows of proc
        set output to output & name of proc & tab & name of win & linefeed
      end repeat
    end if
  end repeat
end tell
return output
""".strip()
            result = _osascript(script, timeout=15)
            if result.get("ok"):
                windows = []
                for line in str(result.get("stdout") or "").splitlines():
                    app, _, title = line.partition("\t")
                    if title.strip():
                        windows.append(DesktopWindow(id=None, app=app.strip(), title=title.strip(), platform=self.platform).to_dict())
                return {
                    "ok": True,
                    "kind": "desktop_window_list",
                    "platform": self.platform,
                    "windows": windows,
                }
            return {**result, "kind": "desktop_window_list", "platform": self.platform}

        if self.platform == "linux" and shutil.which("wmctrl"):
            result = _run(["wmctrl", "-l"])
            if result.get("ok"):
                windows = []
                for line in str(result.get("stdout") or "").splitlines():
                    parts = line.split(None, 3)
                    if len(parts) >= 4:
                        windows.append(DesktopWindow(id=parts[0], title=parts[3], platform=self.platform).to_dict())
                return {
                    "ok": True,
                    "kind": "desktop_window_list",
                    "platform": self.platform,
                    "windows": windows,
                }
            return {**result, "kind": "desktop_window_list", "platform": self.platform}

        if self.platform == "windows":
            script = (
                "Get-Process | Where-Object {$_.MainWindowTitle} | "
                "ForEach-Object { Write-Output ($_.Id.ToString()+\"`t\"+$_.ProcessName+\"`t\"+$_.MainWindowTitle) }"
            )
            result = _powershell(script)
            if result.get("ok"):
                windows = []
                for line in str(result.get("stdout") or "").splitlines():
                    window_id, _, rest = line.partition("\t")
                    app, _, title = rest.partition("\t")
                    if title.strip():
                        windows.append(DesktopWindow(id=window_id.strip(), app=app.strip(), title=title.strip(), platform=self.platform).to_dict())
                return {
                    "ok": True,
                    "kind": "desktop_window_list",
                    "platform": self.platform,
                    "windows": windows,
                }
            return {**result, "kind": "desktop_window_list", "platform": self.platform}

        return {
            "ok": False,
            "kind": "desktop_window_list",
            "platform": self.platform,
            "error": "Window listing is not supported on this platform.",
        }

    def open_app(self, app_name: str, *, proof_label: str = "desktop-app-open") -> dict[str, Any]:
        action: dict[str, Any] = {
            "kind": "desktop_app_open",
            "app_name": app_name,
            "visible": self.visible,
            "platform": self.platform,
        }

        if not self.visible:
            action.update({
                "ok": True,
                "skipped": True,
                "reason": "visible actions are disabled for this WorkMode run",
            })
            return action

        command: list[str] | None = None
        if self.platform == "macos":
            command = ["open", "-a", app_name]
        elif self.platform == "linux":
            executable = (
                shutil.which(app_name)
                or shutil.which(app_name.lower())
                or shutil.which(app_name.lower().replace(" ", "-"))
                or shutil.which(app_name.lower().replace(" ", ""))
            )
            if executable:
                command = [executable]
        elif self.platform == "windows":
            command = ["cmd", "/c", "start", "", app_name]

        if command is None:
            action.update({
                "ok": False,
                "error": f"No supported desktop opener for application: {app_name}",
            })
            return action

        result = _spawn(command)
        action.update(result)
        action["command"] = command
        if result.get("ok"):
            self.with_proof(action, label=proof_label)
        return action

    def open_path(self, path: str | Path, *, proof_label: str = "desktop-path-open") -> dict[str, Any]:
        target = str(path)
        action: dict[str, Any] = {
            "kind": "desktop_path_open",
            "target": target,
            "visible": self.visible,
            "platform": self.platform,
        }
        if not self.visible:
            action.update({"ok": True, "skipped": True, "reason": "visible actions are disabled"})
            return action

        command: list[str] | None = None
        if self.platform == "macos":
            command = ["open", target]
        elif self.platform == "linux" and shutil.which("xdg-open"):
            command = ["xdg-open", target]
        elif self.platform == "windows":
            command = ["cmd", "/c", "start", "", target]

        if command is None:
            action.update({"ok": False, "error": "No supported path opener is available."})
            return action

        result = _spawn(command)
        action.update(result)
        if result.get("ok"):
            self.with_proof(action, label=proof_label)
        return action

    def open_url(self, url: str, *, proof_label: str = "desktop-url-open") -> dict[str, Any]:
        action: dict[str, Any] = {
            "kind": "desktop_url_open",
            "target": url,
            "url": url,
            "visible": self.visible,
            "platform": self.platform,
        }
        if not self.visible:
            action.update({"ok": True, "skipped": True, "reason": "visible actions are disabled"})
            return action

        command: list[str] | None = None
        if self.platform == "macos":
            command = ["open", url]
        elif self.platform == "linux" and shutil.which("xdg-open"):
            command = ["xdg-open", url]
        elif self.platform == "windows":
            command = ["cmd", "/c", "start", "", url]

        try:
            if command is None:
                opened = webbrowser.open(url)
                action.update({"ok": opened, "command": "webbrowser.open"})
            else:
                action.update(_spawn(command))
                action["command"] = command
        except Exception as exc:
            action.update({
                "ok": False,
                "command": command or "webbrowser.open",
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

        if action.get("ok"):
            self.with_proof(action, label=proof_label)
        return action

    def focus_app(self, app_name: str, *, proof_label: str = "desktop-app-focus") -> dict[str, Any]:
        action: dict[str, Any] = {
            "kind": "desktop_app_focus",
            "app_name": app_name,
            "visible": self.visible,
            "platform": self.platform,
        }
        if not self.visible:
            action.update({"ok": True, "skipped": True, "reason": "visible actions are disabled"})
            return action

        if self.platform == "macos":
            result = _osascript(f'tell application "{app_name}" to activate')
        elif self.platform == "linux":
            if shutil.which("wmctrl"):
                result = _run(["wmctrl", "-a", app_name])
            else:
                result = {"ok": False, "status": "missing", "error": "wmctrl is not available."}
        elif self.platform == "windows":
            safe_app_name = _powershell_quote(app_name)
            script = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"if ($ws.AppActivate('{safe_app_name}')) {{ exit 0 }} else {{ exit 1 }}"
            )
            result = _powershell(script)
        else:
            result = {"ok": False, "status": "failed", "error": "Unsupported platform."}

        action.update(result)
        if result.get("ok"):
            self.with_proof(action, label=proof_label)
        return action

    def focus_window(self, title: str, *, proof_label: str = "desktop-window-focus") -> dict[str, Any]:
        action: dict[str, Any] = {
            "kind": "desktop_window_focus",
            "title": title,
            "visible": self.visible,
            "platform": self.platform,
        }
        if not self.visible:
            action.update({"ok": True, "skipped": True, "reason": "visible actions are disabled"})
            return action

        if self.platform == "macos":
            escaped = title.replace('"', '\\"')
            script = f"""
tell application "System Events"
  repeat with proc in application processes
    repeat with win in windows of proc
      if name of win contains "{escaped}" then
        set frontmost of proc to true
        perform action "AXRaise" of win
        return name of proc & tab & name of win
      end if
    end repeat
  end repeat
end tell
error "window not found"
""".strip()
            result = _osascript(script)
        elif self.platform == "linux":
            if shutil.which("wmctrl"):
                result = _run(["wmctrl", "-a", title])
            else:
                result = {"ok": False, "status": "missing", "error": "wmctrl is not available."}
        elif self.platform == "windows":
            safe_title = _powershell_quote(title)
            script = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"if ($ws.AppActivate('{safe_title}')) {{ exit 0 }} else {{ exit 1 }}"
            )
            result = _powershell(script)
        else:
            result = {"ok": False, "status": "failed", "error": "Unsupported platform."}

        action.update(result)
        if result.get("ok"):
            self.with_proof(action, label=proof_label)
        return action

    def move_resize(
        self,
        *,
        rect: DesktopRect | dict[str, Any] | list[Any] | tuple[Any, ...] | str | None = None,
        app_name: str | None = None,
        title: str | None = None,
        role: str = "default",
        proof_label: str = "desktop-window-position",
    ) -> dict[str, Any]:
        target_rect = parse_rect(rect) or self.default_stage_rect(role)
        action: dict[str, Any] = {
            "kind": "desktop_window_position",
            "app_name": app_name,
            "title": title,
            "role": role,
            "rect": target_rect.to_dict() if target_rect else None,
            "visible": self.visible,
            "platform": self.platform,
        }
        if not self.visible:
            action.update({"ok": True, "skipped": True, "reason": "visible actions are disabled"})
            return action
        if target_rect is None:
            action.update({"ok": False, "error": "No window rectangle is available."})
            return action

        if self.platform == "macos":
            process_name = app_name or ""
            if not process_name and title:
                focused = self.focus_window(title, proof_label=f"{proof_label}-focus")
                if not focused.get("ok"):
                    action.update({"ok": False, "focus": focused, "error": "Unable to focus target window."})
                    return action
                active = self.active_window()
                process_name = str(((active.get("window") or {}).get("app")) or "")
            if not process_name:
                active = self.active_window()
                process_name = str(((active.get("window") or {}).get("app")) or "")
            if not process_name:
                action.update({"ok": False, "error": "No macOS process name is available for positioning."})
                return action
            escaped_app = process_name.replace('"', '\\"')
            script = f"""
tell application "System Events"
  tell process "{escaped_app}"
    if (count of windows) = 0 then error "no windows"
    set position of front window to {{{target_rect.x}, {target_rect.y}}}
    set size of front window to {{{target_rect.width}, {target_rect.height}}}
    return name of front window
  end tell
end tell
""".strip()
            result = _osascript(script)
        elif self.platform == "linux":
            window_ref = title or app_name
            if not window_ref:
                active = self.active_window()
                window_ref = str(((active.get("window") or {}).get("title")) or "")
            if not window_ref:
                action.update({"ok": False, "error": "No Linux window reference is available."})
                return action
            if shutil.which("wmctrl"):
                result = _run([
                    "wmctrl",
                    "-r",
                    window_ref,
                    "-e",
                    f"0,{target_rect.x},{target_rect.y},{target_rect.width},{target_rect.height}",
                ])
            elif shutil.which("xdotool"):
                search = _run(["xdotool", "search", "--name", window_ref])
                window_id = str(search.get("stdout") or "").splitlines()[0] if search.get("ok") and search.get("stdout") else ""
                if window_id:
                    result = _run(["xdotool", "windowmove", window_id, str(target_rect.x), str(target_rect.y)])
                    if result.get("ok"):
                        result = _run(["xdotool", "windowsize", window_id, str(target_rect.width), str(target_rect.height)])
                else:
                    result = {"ok": False, "status": "not_found", "error": "window not found", "title": window_ref}
            else:
                result = {"ok": False, "status": "missing", "error": "wmctrl or xdotool is required."}
        elif self.platform == "windows":
            target = title or app_name or ""
            if not target:
                action.update({"ok": False, "error": "No Windows target title/app is available."})
                return action
            safe_target = _powershell_quote(target)
            script = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {{
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}}
"@
$p = Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{safe_target}*' -or $_.ProcessName -like '*{safe_target}*' }} | Select-Object -First 1
if (-not $p) {{ Write-Error 'window not found'; exit 1 }}
[Win32]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
if ([Win32]::MoveWindow($p.MainWindowHandle, {target_rect.x}, {target_rect.y}, {target_rect.width}, {target_rect.height}, $true)) {{ exit 0 }} else {{ exit 1 }}
""".strip()
            result = _powershell(script)
        else:
            result = {"ok": False, "status": "failed", "error": "Unsupported platform."}

        action.update(result)
        if result.get("ok"):
            self.with_proof(action, label=proof_label)
        return action

    def collect_screenshots(self, actions: list[dict[str, Any]]) -> list[str]:
        paths = []
        for action in actions:
            path = _screenshot_path(action)
            if path:
                paths.append(path)
        return list(dict.fromkeys(paths))

    def snapshot_state(self, *, proof_label: str = "desktop-state") -> dict[str, Any]:
        actions = [
            self.capabilities(),
            self.active_window(),
            self.list_windows(),
        ]
        screenshot_action = {
            "kind": "desktop_state_screenshot",
            "ok": True,
            "visible": self.visible,
            "platform": self.platform,
        }
        self.with_proof(screenshot_action, label=proof_label)
        actions.append(screenshot_action)
        return {
            "ok": any(action.get("ok") for action in actions),
            "kind": "desktop_state",
            "platform": self.platform,
            "actions": actions,
            "screenshots": self.collect_screenshots(actions),
        }
