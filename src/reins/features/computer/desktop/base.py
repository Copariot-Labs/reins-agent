from __future__ import annotations

from abc import ABC, abstractmethod


class DesktopBackend(ABC):
    @abstractmethod
    def doctor(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def open_url(self, url: str, app: str | None = None) -> dict:
        raise NotImplementedError

    @abstractmethod
    def open_file(self, path: str, app: str | None = None) -> dict:
        raise NotImplementedError

    @abstractmethod
    def screenshot(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def activate_app(self, app_name: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def type_text(self, text: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def hotkey(self, *keys: str) -> dict:
        raise NotImplementedError