from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Sequence

from reins.compat.bootstrap import get_project_root

DEFAULT_OFFICECLI_BATCH_TIMEOUT_SECONDS = 1_200


class OfficeCliError(RuntimeError):
    pass


class OfficeCliNotAvailable(OfficeCliError):
    pass


class OfficeCliCommandError(OfficeCliError):
    def __init__(
        self,
        *,
        command: Sequence[str],
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.command = list(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        message = stderr.strip() or stdout.strip() or f"Reins Office exited {returncode}"
        super().__init__(message)


@dataclass(slots=True)
class OfficeCliRun:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def officecli_batch_item(args: Sequence[object]) -> dict[str, object] | None:
    """Translate one supported OfficeCLI mutation into a batch item."""
    command = [str(argument) for argument in args]
    if len(command) < 3 or command[0] not in {"add", "set", "remove", "move", "swap"}:
        return None

    verb = command[0]
    target = command[2]
    item: dict[str, object] = {
        "command": verb,
        "parent" if verb == "add" else "path": target,
    }
    position = 3
    if verb == "swap":
        if position >= len(command) or command[position].startswith("--"):
            return None
        item["path2"] = command[position]
        position += 1

    props: dict[str, str] = {}
    field_flags = {
        "--type": "type",
        "--from": "from",
        "--after": "after",
        "--before": "before",
        "--to": "to",
        "--path2": "path2",
    }
    while position < len(command):
        flag = command[position]
        if position + 1 >= len(command):
            return None
        value = command[position + 1]
        position += 2
        if flag == "--prop":
            name, separator, prop_value = value.partition("=")
            if not separator or not name:
                return None
            props[name] = prop_value
        elif flag == "--index":
            try:
                item["index"] = int(value)
            except ValueError:
                return None
        elif flag in field_flags:
            item[field_flags[flag]] = value
        else:
            # Find/replace and any future CLI-only flags stay on the proven
            # sequential path until OfficeCLI exposes an equivalent batch field.
            return None

    if props:
        item["props"] = props
    return item


def _candidate_vendor_bins() -> list[Path]:
    root = get_project_root() / "vendor" / "OfficeCLI"
    system = platform.system().lower()
    machine = platform.machine().lower()
    asset_names: list[str] = ["officecli"]

    if system == "darwin":
        asset_names.insert(0, "officecli-mac-arm64" if machine == "arm64" else "officecli-mac-x64")
    elif system == "linux":
        asset_names.insert(0, "officecli-linux-arm64" if machine in {"aarch64", "arm64"} else "officecli-linux-x64")
    elif system == "windows":
        asset_names.insert(0, "officecli-win-arm64.exe" if machine in {"arm64", "aarch64"} else "officecli-win-x64.exe")

    candidates = [
        root / "officecli",
        root / "officecli.exe",
        root / "bin" / "officecli",
        root / "bin" / "officecli.exe",
        root / "build" / "officecli",
        root / "build" / "officecli.exe",
    ]

    for name in asset_names:
        candidates.extend(
            [
                root / "bin" / "release" / name,
                root / "bin" / "debug" / name,
                root / "bin" / "Release" / name,
                root / "bin" / "Debug" / name,
            ]
        )

    for pattern in (
        "src/officecli/bin/Release/*/*/publish/officecli",
        "src/officecli/bin/Release/*/*/publish/officecli.exe",
        "src/officecli/bin/Debug/*/*/officecli",
        "src/officecli/bin/Debug/*/*/officecli.exe",
    ):
        candidates.extend(root.glob(pattern))

    return candidates


def find_officecli_binary() -> str | None:
    configured = os.environ.get("OFFICECLI_BIN", "").strip()
    if configured:
        expanded = Path(os.path.expandvars(configured)).expanduser()
        if expanded.is_absolute() or os.sep in configured:
            return str(expanded)
        found = shutil.which(configured)
        return found or configured

    found = shutil.which("officecli")
    if found:
        return found

    for candidate in _candidate_vendor_bins():
        if candidate.exists() and candidate.is_file() and candidate.suffix != ".pdb":
            return str(candidate)

    return None


def officecli_setup_hint() -> str:
    return "Reins Office support is unavailable. Restart Reins or reinstall the desktop app."


class OfficeCliClient:
    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_officecli_binary()
        self.history: list[OfficeCliRun] = []

    @property
    def command_count(self) -> int:
        return len(self.history)

    def require_binary(self) -> str:
        if not self.binary:
            raise OfficeCliNotAvailable(officecli_setup_hint())
        return self.binary

    def run(
        self,
        args: Sequence[object],
        *,
        timeout: int = 60,
        allowed_returncodes: tuple[int, ...] = (0,),
        env_overrides: dict[str, str] | None = None,
    ) -> OfficeCliRun:
        binary = self.require_binary()
        command = [binary, *[str(arg) for arg in args]]
        env = os.environ.copy()
        env.setdefault("OFFICECLI_SKIP_UPDATE", "1")
        if env_overrides:
            env.update(env_overrides)

        try:
            completed = subprocess.run(
                command,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OfficeCliNotAvailable(officecli_setup_hint()) from exc

        result = OfficeCliRun(
            args=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        self.history.append(result)

        if completed.returncode not in allowed_returncodes:
            raise OfficeCliCommandError(
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        return result

    def run_batch(
        self,
        path: str | Path,
        commands: Sequence[dict[str, object]],
        *,
        timeout: int = DEFAULT_OFFICECLI_BATCH_TIMEOUT_SECONDS,
        allowed_returncodes: tuple[int, ...] = (0, 2),
    ) -> OfficeCliRun:
        """Apply mutations in one atomic OfficeCLI open/save cycle."""
        if not commands:
            return OfficeCliRun(args=[], returncode=0, stdout="", stderr="")

        input_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                prefix="reins-office-batch-",
                delete=False,
            ) as batch_file:
                json.dump(list(commands), batch_file, ensure_ascii=False)
                input_path = Path(batch_file.name)
            return self.run(
                ["batch", path, "--input", input_path, "--stop-on-error", "--json"],
                timeout=timeout,
                allowed_returncodes=allowed_returncodes,
                env_overrides={
                    "OFFICECLI_NO_AUTO_RESIDENT": "1",
                    "OFFICECLI_BATCH_ALLOW_STDIN_REDIRECT": "1",
                },
            )
        finally:
            if input_path is not None:
                try:
                    input_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def version(self) -> str | None:
        result = self.run(["--version"], timeout=10)
        return (result.stdout or result.stderr).strip() or None


def officecli_status() -> dict[str, object]:
    client = OfficeCliClient()
    status: dict[str, object] = {
        "available": False,
        "binary": client.binary,
        "version": None,
        "error": None,
        "setup_hint": officecli_setup_hint(),
    }

    try:
        status["version"] = client.version()
        status["available"] = True
    except Exception as exc:
        status["error"] = str(exc)

    return status
