from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkContext:
    """
    Shared execution memory for multi-step reasoning.
    """

    case_id: str
    state: dict[str, Any] = field(default_factory=dict)

    screenshots: list[str] = field(default_factory=list)
    ocr_texts: list[str] = field(default_factory=list)
    browser_pages: list[dict[str, Any]] = field(default_factory=list)

    def add_screenshot(self, path: str):
        self.screenshots.append(path)

    def add_ocr(self, text: str):
        self.ocr_texts.append(text)

    def add_page(self, page: dict[str, Any]):
        self.browser_pages.append(page)