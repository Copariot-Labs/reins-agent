from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import platform
import shutil
import subprocess
import time
from typing import Sequence

from reins.features.wechat.errors import WeChatDependencyError, WeChatError, WeChatUnsupportedPlatform


@dataclass(slots=True)
class WeChatResult:
    ok: bool
    action: str
    platform: str
    message: str = ""
    contact: str | None = None
    file: str | None = None
    sent: bool = False
    draft_only: bool = False
    warnings: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ok": self.ok,
            "action": self.action,
            "platform": self.platform,
            "message": self.message,
            "sent": self.sent,
            "draft_only": self.draft_only,
            "warnings": self.warnings,
            "details": self.details,
        }
        if self.contact is not None:
            payload["contact"] = self.contact
        if self.file is not None:
            payload["file"] = self.file
        if self.error:
            payload["error"] = self.error
        return payload


class CommandRunner:
    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.commands: list[list[str]] = []

    def run(
        self,
        args: Sequence[str],
        *,
        input_text: str | None = None,
        check: bool = True,
        timeout: float = 15,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(arg) for arg in args]
        self.commands.append(command)
        if self.dry_run:
            return subprocess.CompletedProcess(command, 0, "", "")
        try:
            return subprocess.run(
                command,
                input=input_text,
                text=True,
                capture_output=True,
                check=check,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise WeChatDependencyError(f"Missing command: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            detail = f": {stderr}" if stderr else ""
            raise WeChatError(f"Command failed: {' '.join(command)}{detail}") from exc
        except subprocess.TimeoutExpired as exc:
            raise WeChatError(f"Command timed out: {' '.join(command)}") from exc

    def popen(self, args: Sequence[str]) -> None:
        command = [str(arg) for arg in args]
        self.commands.append(command)
        if self.dry_run:
            return
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError as exc:
            raise WeChatDependencyError(f"Missing command: {command[0]}") from exc


class BaseWeChatDriver:
    platform_name = "unknown"

    def __init__(self, *, dry_run: bool = False, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner(dry_run=dry_run)

    @property
    def dry_run(self) -> bool:
        return self.runner.dry_run

    def delay(self, seconds: float | None = None) -> None:
        value = seconds if seconds is not None else float(os.environ.get("REINS_WECHAT_STEP_DELAY", "0.35") or "0.35")
        if value > 0 and not self.dry_run:
            time.sleep(value)

    def doctor(self) -> WeChatResult:
        raise NotImplementedError

    def open(self) -> WeChatResult:
        raise NotImplementedError

    def search_contact(self, name: str) -> WeChatResult:
        raise NotImplementedError

    def draft_message(self, contact: str, message: str) -> WeChatResult:
        self.search_contact(contact)
        self.set_clipboard(message)
        self.paste_clipboard()
        return WeChatResult(
            ok=True,
            action="draft_message",
            platform=self.platform_name,
            contact=contact,
            message="Message drafted. It was NOT sent.",
            draft_only=True,
            details={"message_chars": len(message), "commands": self.runner.commands},
        )

    def send_current_draft(self, *, confirm: bool, send_key: str = "enter") -> WeChatResult:
        if not confirm:
            return WeChatResult(
                ok=False,
                action="send_current_draft",
                platform=self.platform_name,
                message="Missing confirmation. Draft was NOT sent.",
                sent=False,
                error="--confirm is required before sending",
            )
        self.press_send(send_key)
        return WeChatResult(
            ok=True,
            action="send_current_draft",
            platform=self.platform_name,
            message="Confirmed send command executed.",
            sent=True,
            details={"send_key": send_key, "commands": self.runner.commands},
        )

    def send_message(self, contact: str, message: str, *, confirm: bool, send_key: str = "enter") -> WeChatResult:
        draft = self.draft_message(contact, message)
        if not confirm:
            draft.message = "Message drafted. It was NOT sent because --confirm was not provided."
            draft.sent = False
            draft.draft_only = True
            draft.error = "missing_confirm"
            return draft
        sent = self.send_current_draft(confirm=True, send_key=send_key)
        sent.action = "send_message"
        sent.contact = contact
        sent.details["message_chars"] = len(message)
        return sent

    def draft_file(self, contact: str, file_path: str, message: str = "") -> WeChatResult:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return WeChatResult(
                ok=False,
                action="draft_file",
                platform=self.platform_name,
                contact=contact,
                file=str(path),
                message="File not found. Nothing was sent.",
                error=f"File not found: {path}",
            )
        self.search_contact(contact)
        self.copy_file_to_clipboard(path)
        self.paste_clipboard()
        if message:
            self.delay()
            self.set_clipboard(message)
            self.paste_clipboard()
        return WeChatResult(
            ok=True,
            action="draft_file",
            platform=self.platform_name,
            contact=contact,
            file=str(path),
            message="File draft prepared. It was NOT sent.",
            draft_only=True,
            details={"message_chars": len(message), "commands": self.runner.commands},
        )

    def send_file(self, contact: str, file_path: str, message: str = "", *, confirm: bool, send_key: str = "enter") -> WeChatResult:
        draft = self.draft_file(contact, file_path, message)
        if not draft.ok:
            return draft
        if not confirm:
            draft.message = "File draft prepared. It was NOT sent because --confirm was not provided."
            draft.error = "missing_confirm"
            return draft
        sent = self.send_current_draft(confirm=True, send_key=send_key)
        sent.action = "send_file"
        sent.contact = contact
        sent.file = str(Path(file_path).expanduser().resolve())
        return sent

    def set_clipboard(self, text: str) -> None:
        raise NotImplementedError

    def copy_file_to_clipboard(self, path: Path) -> None:
        raise NotImplementedError

    def paste_clipboard(self) -> None:
        raise NotImplementedError

    def press_send(self, send_key: str) -> None:
        raise NotImplementedError


def _apple_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MacOSWeChatDriver(BaseWeChatDriver):
    platform_name = "macos"

    def app_names(self) -> list[str]:
        configured = os.environ.get("REINS_WECHAT_MAC_APP", "").strip()
        return [configured] if configured else ["WeChat", "微信"]

    def doctor(self) -> WeChatResult:
        missing = [name for name in ["open", "osascript", "pbcopy"] if not shutil.which(name)]
        return WeChatResult(
            ok=not missing,
            action="doctor",
            platform=self.platform_name,
            message="macOS WeChat automation dependencies checked.",
            details={
                "required_commands": ["open", "osascript", "pbcopy"],
                "missing_commands": missing,
                "required_permissions": ["Accessibility", "Automation"],
                "app_candidates": self.app_names(),
            },
            warnings=[] if not missing else [f"Missing command: {name}" for name in missing],
        )

    def osascript(self, script: str) -> None:
        self.runner.run(["osascript", "-e", script], timeout=20)

    def open(self) -> WeChatResult:
        errors: list[str] = []
        for app_name in self.app_names():
            try:
                self.runner.run(["open", "-a", app_name], timeout=20)
                self.delay(0.8)
                return WeChatResult(
                    ok=True,
                    action="open",
                    platform=self.platform_name,
                    message=f"WeChat app activated: {app_name}",
                    details={"app": app_name, "commands": self.runner.commands},
                )
            except WeChatError as exc:
                errors.append(str(exc))
        raise WeChatError("Could not open WeChat. Tried: " + ", ".join(self.app_names()) + ". " + " | ".join(errors))

    def hotkey(self, key: str, modifiers: Sequence[str] = ()) -> None:
        modifier_map = {
            "cmd": "command down",
            "command": "command down",
            "ctrl": "control down",
            "control": "control down",
            "alt": "option down",
            "option": "option down",
            "shift": "shift down",
        }
        mapped = [modifier_map.get(item.lower(), item) for item in modifiers]
        if mapped:
            script = f'tell application "System Events" to keystroke {_apple_string(key)} using {{{", ".join(mapped)}}}'
        else:
            script = f'tell application "System Events" to keystroke {_apple_string(key)}'
        self.osascript(script)
        self.delay()

    def key_code(self, code: int, modifiers: Sequence[str] = ()) -> None:
        modifier_map = {
            "cmd": "command down",
            "command": "command down",
            "ctrl": "control down",
            "control": "control down",
            "alt": "option down",
            "option": "option down",
            "shift": "shift down",
        }
        mapped = [modifier_map.get(item.lower(), item) for item in modifiers]
        suffix = f" using {{{', '.join(mapped)}}}" if mapped else ""
        self.osascript(f'tell application "System Events" to key code {code}{suffix}')
        self.delay()

    def search_contact(self, name: str) -> WeChatResult:
        self.open()
        search_hotkey = os.environ.get("REINS_WECHAT_MAC_SEARCH_HOTKEY", "command+f")
        modifiers, key = parse_hotkey(search_hotkey)
        self.hotkey(key, modifiers)
        self.set_clipboard(name)
        self.hotkey("a", ["command"])
        self.paste_clipboard()
        self.key_code(36)
        return WeChatResult(
            ok=True,
            action="search_contact",
            platform=self.platform_name,
            contact=name,
            message="Contact search executed. Verify the selected chat before sending.",
            warnings=["Contact selection is keyboard-driven; visually verify the selected WeChat conversation."],
            details={"search_hotkey": search_hotkey, "commands": self.runner.commands},
        )

    def set_clipboard(self, text: str) -> None:
        self.runner.run(["pbcopy"], input_text=text, timeout=10)

    def copy_file_to_clipboard(self, path: Path) -> None:
        script = f"set the clipboard to (POSIX file {_apple_string(str(path))} as alias)"
        self.osascript(script)

    def paste_clipboard(self) -> None:
        self.hotkey("v", ["command"])

    def press_send(self, send_key: str) -> None:
        normalized = send_key.strip().lower()
        if normalized in {"cmd-enter", "command-enter", "cmd+enter", "command+enter"}:
            self.key_code(36, ["command"])
            return
        if normalized in {"enter", "return"}:
            self.key_code(36)
            return
        raise WeChatError(f"Unsupported macOS send key: {send_key}")


class LinuxWeChatDriver(BaseWeChatDriver):
    platform_name = "linux"

    def doctor(self) -> WeChatResult:
        missing: list[str] = []
        if not self._clipboard_tool():
            missing.append("wl-copy or xclip or xsel")
        if not shutil.which("xdotool"):
            missing.append("xdotool")
        if not self._has_launcher():
            missing.append("wechat launcher")
        warnings = [f"Missing dependency: {item}" for item in missing]
        if not shutil.which("wmctrl"):
            warnings.append("wmctrl is optional but improves WeChat window focusing.")
        return WeChatResult(
            ok=not missing,
            action="doctor",
            platform=self.platform_name,
            message="Linux WeChat automation dependencies checked.",
            warnings=warnings,
            details={
                "required_commands": ["xdotool", "wl-copy or xclip or xsel", "wechat launcher"],
                "optional_commands": ["wmctrl"],
                "missing": missing,
                "launcher_candidates": self.launcher_candidates(),
                "display": os.environ.get("XDG_SESSION_TYPE") or os.environ.get("DISPLAY") or "",
            },
        )

    def launcher_candidates(self) -> list[str]:
        configured = os.environ.get("REINS_WECHAT_LINUX_APP", "").strip()
        if configured:
            return [configured]
        return ["wechat", "weixin", "wechat-uos", "electronic-wechat", "com.tencent.WeChat"]

    def _has_launcher(self) -> bool:
        if self.dry_run:
            return True
        return any(shutil.which(item) for item in self.launcher_candidates()) or shutil.which("gtk-launch") is not None

    def _clipboard_tool(self) -> str | None:
        if self.dry_run:
            return "wl-copy"
        for name in ["wl-copy", "xclip", "xsel"]:
            if shutil.which(name):
                return name
        return None

    def open(self) -> WeChatResult:
        launched = False
        if self.dry_run:
            self.runner.popen([self.launcher_candidates()[0]])
            launched = True
        for candidate in self.launcher_candidates():
            if launched:
                break
            executable = shutil.which(candidate)
            if executable:
                self.runner.popen([executable])
                launched = True
                break
        if not launched and shutil.which("gtk-launch"):
            for desktop_id in self.launcher_candidates():
                try:
                    self.runner.run(["gtk-launch", desktop_id], check=True, timeout=8)
                    launched = True
                    break
                except WeChatError:
                    continue
        if not launched:
            raise WeChatDependencyError("Could not find a WeChat launcher. Set REINS_WECHAT_LINUX_APP to the app command or desktop id.")
        self.delay(1.0)
        self.activate_window()
        return WeChatResult(
            ok=True,
            action="open",
            platform=self.platform_name,
            message="WeChat launch/focus command executed.",
            details={"launcher_candidates": self.launcher_candidates(), "commands": self.runner.commands},
        )

    def activate_window(self) -> None:
        if not shutil.which("wmctrl"):
            return
        for title in ["WeChat", "微信", "Weixin"]:
            try:
                self.runner.run(["wmctrl", "-a", title], check=True, timeout=5)
                self.delay()
                return
            except WeChatError:
                continue

    def key(self, value: str) -> None:
        if not self.dry_run and not shutil.which("xdotool"):
            raise WeChatDependencyError("xdotool is required for Linux WeChat keyboard automation")
        self.runner.run(["xdotool", "key", value], timeout=10)
        self.delay()

    def search_contact(self, name: str) -> WeChatResult:
        self.open()
        search_hotkey = os.environ.get("REINS_WECHAT_LINUX_SEARCH_HOTKEY", "ctrl+f")
        self.key(to_xdotool_hotkey(search_hotkey))
        self.set_clipboard(name)
        self.key("ctrl+a")
        self.paste_clipboard()
        self.key("Return")
        return WeChatResult(
            ok=True,
            action="search_contact",
            platform=self.platform_name,
            contact=name,
            message="Contact search executed. Verify the selected chat before sending.",
            warnings=["Contact selection is keyboard-driven; visually verify the selected WeChat conversation."],
            details={"search_hotkey": search_hotkey, "commands": self.runner.commands},
        )

    def set_clipboard(self, text: str) -> None:
        tool = self._clipboard_tool()
        if not tool:
            raise WeChatDependencyError("Install wl-copy, xclip, or xsel for clipboard support")
        if tool == "wl-copy":
            self.runner.run(["wl-copy"], input_text=text, timeout=10)
        elif tool == "xclip":
            self.runner.run(["xclip", "-selection", "clipboard"], input_text=text, timeout=10)
        else:
            self.runner.run(["xsel", "--clipboard", "--input"], input_text=text, timeout=10)

    def copy_file_to_clipboard(self, path: Path) -> None:
        uri = path.as_uri()
        tool = self._clipboard_tool()
        if not tool:
            raise WeChatDependencyError("Install wl-copy, xclip, or xsel for clipboard support")
        if tool == "wl-copy":
            self.runner.run(["wl-copy", "--type", "text/uri-list"], input_text=uri, timeout=10)
        elif tool == "xclip":
            self.runner.run(["xclip", "-selection", "clipboard", "-t", "text/uri-list"], input_text=uri, timeout=10)
        else:
            self.runner.run(["xsel", "--clipboard", "--input"], input_text=uri, timeout=10)

    def paste_clipboard(self) -> None:
        self.key("ctrl+v")

    def press_send(self, send_key: str) -> None:
        normalized = send_key.strip().lower()
        if normalized in {"enter", "return"}:
            self.key("Return")
            return
        if normalized in {"ctrl-enter", "control-enter", "ctrl+enter", "control+enter"}:
            self.key("ctrl+Return")
            return
        raise WeChatError(f"Unsupported Linux send key: {send_key}")


def parse_hotkey(value: str) -> tuple[list[str], str]:
    parts = [part.strip().lower() for part in value.replace("-", "+").split("+") if part.strip()]
    if not parts:
        return ["command"], "f"
    return parts[:-1], parts[-1]


def to_xdotool_hotkey(value: str) -> str:
    parts = [part.strip().lower() for part in value.replace("-", "+").split("+") if part.strip()]
    mapping = {
        "control": "ctrl",
        "cmd": "super",
        "command": "super",
        "return": "Return",
        "enter": "Return",
    }
    return "+".join(mapping.get(part, part) for part in parts)


def current_driver(*, dry_run: bool = False) -> BaseWeChatDriver:
    system = platform.system().lower()
    if system == "darwin":
        return MacOSWeChatDriver(dry_run=dry_run)
    if system == "linux":
        return LinuxWeChatDriver(dry_run=dry_run)
    if system == "windows":
        raise WeChatUnsupportedPlatform("Windows WeChat automation is planned but not implemented yet.")
    raise WeChatUnsupportedPlatform(f"Unsupported platform for WeChat automation: {system or 'unknown'}")
