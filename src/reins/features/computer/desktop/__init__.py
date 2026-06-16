from __future__ import annotations

from reins.features.computer.desktop.base import DesktopBackend
from reins.features.computer.platform import OperatingSystem, current_os


def get_desktop_backend() -> DesktopBackend:
    os_name = current_os()

    if os_name == OperatingSystem.MACOS:
        from reins.features.computer.desktop.macos import MacOSDesktopBackend

        return MacOSDesktopBackend()

    # if os_name == OperatingSystem.WINDOWS:
    #     from reins.features.computer.desktop.windows import WindowsDesktopBackend

    #     return WindowsDesktopBackend()

    # if os_name == OperatingSystem.LINUX:
    #     from reins.features.computer.desktop.linux import LinuxDesktopBackend

    #     return LinuxDesktopBackend()

    raise RuntimeError(f"Unsupported operating system: {os_name}")