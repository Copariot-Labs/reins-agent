from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Sequence

from reins.compat.bootstrap import get_project_root


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
