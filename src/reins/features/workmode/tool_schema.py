from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class ToolSchema:
    name: str
    required_fields: list[str]


TOOL_REGISTRY: Dict[str, ToolSchema] = {
    "browser_source": ToolSchema(
        name="browser_source",
        required_fields=["title", "description", "worker"]
    ),
    "desktop_capture": ToolSchema(
        name="desktop_capture",
        required_fields=["title", "description", "worker"]
    ),
    "office_generate": ToolSchema(
        name="office_generate",
        required_fields=["title", "description", "worker"]
    ),
}