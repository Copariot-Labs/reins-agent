from __future__ import annotations

import platform
from enum import Enum


class OperatingSystem(str, Enum):
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


def current_os() -> OperatingSystem:
    name = platform.system().lower()

    if name == "darwin":
        return OperatingSystem.MACOS

    if name == "windows":
        return OperatingSystem.WINDOWS

    if name == "linux":
        return OperatingSystem.LINUX

    return OperatingSystem.UNKNOWN