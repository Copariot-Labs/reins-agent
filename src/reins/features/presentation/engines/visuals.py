from __future__ import annotations

import re
import unicodedata

from dataclasses import dataclass

from reins.features.presentation.models import PresentationStyle


@dataclass(frozen=True, slots=True)
class PresentationPalette:
    background: str
    surface: str
    text: str
    muted: str
    primary: str
    accent: str
    secondary: str


PALETTES: dict[PresentationStyle, PresentationPalette] = {
    PresentationStyle.MODERN: PresentationPalette(
        background="F4F5F7",
        surface="FFFFFF",
        text="15171A",
        muted="667085",
        primary="1D4ED8",
        accent="E63946",
        secondary="008F86",
    ),
    PresentationStyle.TECH: PresentationPalette(
        background="07111F",
        surface="102235",
        text="F2F7FF",
        muted="9CB0C6",
        primary="22D3EE",
        accent="A3E635",
        secondary="FF7A59",
    ),
    PresentationStyle.CORPORATE: PresentationPalette(
        background="F5F7FA",
        surface="FFFFFF",
        text="172033",
        muted="667085",
        primary="123B66",
        accent="008F86",
        secondary="D5A021",
    ),
    PresentationStyle.CREATIVE: PresentationPalette(
        background="FFF7E8",
        surface="FFFFFF",
        text="1A1A1A",
        muted="5E5A54",
        primary="315EFB",
        accent="F04438",
        secondary="F5C542",
    ),
    PresentationStyle.MINIMAL: PresentationPalette(
        background="FAFAF7",
        surface="FFFFFF",
        text="111111",
        muted="666666",
        primary="111111",
        accent="E34234",
        secondary="2D7D6E",
    ),
    PresentationStyle.DARK: PresentationPalette(
        background="111315",
        surface="202428",
        text="FAFAF7",
        muted="A7AFB7",
        primary="5BC0EB",
        accent="FF6B35",
        secondary="9BC53D",
    ),
}


def get_palette(style: PresentationStyle) -> PresentationPalette:
    return PALETTES[style]


def slugify(value: str, fallback: str = "presentation") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", ascii_value).strip("-")
    return (cleaned or fallback).lower()[:80]


def display_width(value: str) -> int:
    width = 0

    for char in value:
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1

    return width


def wrap_display_text(
    value: str,
    *,
    max_width: int,
    max_lines: int,
) -> list[str]:
    words = re.findall(r"\S+\s*", " ".join(str(value or "").split()))
    if not words:
        return []

    lines: list[str] = []
    current = ""

    def push_line() -> None:
        nonlocal current
        if current.strip():
            lines.append(current.strip())
        current = ""

    for word in words:
        pending = word.strip()

        while pending:
            candidate = f"{current} {pending}".strip()
            if display_width(candidate) <= max_width:
                current = candidate
                pending = ""
                continue

            if current:
                push_line()
                if len(lines) >= max_lines:
                    break
                continue

            chunk = ""
            consumed = 0
            for char in pending:
                if chunk and display_width(chunk + char) > max_width:
                    break
                chunk += char
                consumed += 1

            current = chunk
            pending = pending[consumed:]
            push_line()

            if len(lines) >= max_lines:
                break

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        push_line()

    original = " ".join(str(value or "").split())
    rendered = "".join(lines).replace(" ", "")
    comparable = original.replace(" ", "")

    if lines and len(rendered) < len(comparable):
        last = lines[-1].rstrip(" .")
        lines[-1] = f"{last[: max(len(last) - 1, 1)]}..."

    return lines[:max_lines]
