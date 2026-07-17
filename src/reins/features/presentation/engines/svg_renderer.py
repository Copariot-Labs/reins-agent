from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from reins.features.presentation.engines.visuals import (
    PresentationPalette,
    get_palette,
    wrap_display_text,
)
from reins.features.presentation.models import (
    PresentationPlan,
    PresentationSlide,
)


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


def _svg_element(tag: str, attributes: dict[str, object] | None = None):
    return ET.Element(
        f"{{{SVG_NS}}}{tag}",
        {
            key.replace("_", "-"): str(value)
            for key, value in (attributes or {}).items()
        },
    )


def _child(parent, tag: str, **attributes):
    element = _svg_element(tag, attributes)
    parent.append(element)
    return element


def _text(
    parent,
    value: str,
    *,
    x: int,
    y: int,
    size: int,
    color: str,
    weight: int = 500,
    anchor: str | None = None,
    letter_spacing: int | None = None,
):
    attributes: dict[str, object] = {
        "x": x,
        "y": y,
        "font_family": (
            "Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Arial, sans-serif"
        ),
        "font_size": size,
        "font_weight": weight,
        "fill": f"#{color}",
    }
    if anchor:
        attributes["text_anchor"] = anchor
    if letter_spacing is not None:
        attributes["letter_spacing"] = letter_spacing

    element = _child(parent, "text", **attributes)
    element.text = value
    return element


def _background(root, palette: PresentationPalette) -> None:
    group = _child(root, "g", id="background")
    _child(
        group,
        "rect",
        x=0,
        y=0,
        width=1280,
        height=720,
        fill=f"#{palette.background}",
    )
    _child(
        group,
        "rect",
        x=0,
        y=0,
        width=18,
        height=720,
        fill=f"#{palette.accent}",
    )


def _footer(
    root,
    *,
    plan: PresentationPlan,
    slide: PresentationSlide,
    palette: PresentationPalette,
) -> None:
    group = _child(root, "g", id="footer")
    _child(
        group,
        "line",
        x1=62,
        y1=676,
        x2=1218,
        y2=676,
        stroke=f"#{palette.muted}",
        stroke_opacity="0.35",
        stroke_width=1,
    )
    _text(
        group,
        plan.title[:72],
        x=62,
        y=701,
        size=13,
        color=palette.muted,
        weight=600,
    )
    _text(
        group,
        f"{slide.index:02d} / {len(plan.slides):02d}",
        x=1218,
        y=701,
        size=13,
        color=palette.muted,
        weight=700,
        anchor="end",
    )


def _title_slide(
    root,
    *,
    plan: PresentationPlan,
    slide: PresentationSlide,
    palette: PresentationPalette,
) -> None:
    group = _child(root, "g", id="title")
    _text(
        group,
        "REINS PRESENTATION",
        x=82,
        y=106,
        size=16,
        color=palette.accent,
        weight=800,
        letter_spacing=3,
    )

    title_lines = wrap_display_text(
        slide.title,
        max_width=30,
        max_lines=3,
    )
    title_size = 60 if len(title_lines) <= 2 else 50

    for line_index, line in enumerate(title_lines):
        _text(
            group,
            line,
            x=82,
            y=220 + line_index * 74,
            size=title_size,
            color=palette.text,
            weight=900,
        )

    subtitle = slide.subtitle or plan.subtitle or plan.audience
    if subtitle:
        subtitle_lines = wrap_display_text(
            subtitle,
            max_width=70,
            max_lines=2,
        )
        for line_index, line in enumerate(subtitle_lines):
            _text(
                group,
                line,
                x=86,
                y=484 + line_index * 30,
                size=20,
                color=palette.muted,
                weight=500,
            )

    _child(
        group,
        "rect",
        x=82,
        y=566,
        width=190,
        height=10,
        fill=f"#{palette.primary}",
    )
    _child(
        group,
        "rect",
        x=282,
        y=566,
        width=70,
        height=10,
        fill=f"#{palette.secondary}",
    )
    _child(
        group,
        "rect",
        x=362,
        y=566,
        width=34,
        height=10,
        fill=f"#{palette.accent}",
    )

    panel = _child(root, "g", id="title-context")
    _child(
        panel,
        "rect",
        x=936,
        y=82,
        width=272,
        height=506,
        rx=6,
        fill=f"#{palette.surface}",
        stroke=f"#{palette.primary}",
        stroke_width=2,
    )
    _text(
        panel,
        "BRIEF",
        x=972,
        y=138,
        size=14,
        color=palette.primary,
        weight=800,
        letter_spacing=2,
    )
    _text(
        panel,
        f"{len(plan.slides)}",
        x=972,
        y=252,
        size=84,
        color=palette.text,
        weight=900,
    )
    _text(
        panel,
        "SLIDES",
        x=978,
        y=284,
        size=15,
        color=palette.muted,
        weight=700,
        letter_spacing=2,
    )
    _text(
        panel,
        (plan.style.value or "modern").upper(),
        x=978,
        y=410,
        size=18,
        color=palette.accent,
        weight=800,
    )
    _text(
        panel,
        plan.aspect_ratio,
        x=978,
        y=454,
        size=18,
        color=palette.text,
        weight=700,
    )
    _text(
        panel,
        plan.language.upper(),
        x=978,
        y=498,
        size=18,
        color=palette.text,
        weight=700,
    )


def _slide_items(slide: PresentationSlide) -> list[str]:
    items: list[str] = []

    for element in slide.elements:
        if element.title and not element.items:
            items.append(element.title)
        if element.text:
            items.append(element.text)
        items.extend(element.items)

    return [" ".join(item.split()) for item in items if item.strip()][:6]


def _header(
    root,
    *,
    slide: PresentationSlide,
    palette: PresentationPalette,
) -> None:
    group = _child(root, "g", id="header")
    _text(
        group,
        f"SECTION {slide.index:02d}",
        x=62,
        y=72,
        size=13,
        color=palette.accent,
        weight=800,
        letter_spacing=2,
    )

    title_lines = wrap_display_text(
        slide.title,
        max_width=54,
        max_lines=2,
    )
    title_size = 38 if len(title_lines) == 1 else 32
    for line_index, line in enumerate(title_lines):
        _text(
            group,
            line,
            x=62,
            y=122 + line_index * 42,
            size=title_size,
            color=palette.text,
            weight=900,
        )

    _child(
        group,
        "rect",
        x=1120,
        y=54,
        width=98,
        height=8,
        fill=f"#{palette.primary}",
    )


def _card_grid(
    root,
    *,
    items: list[str],
    palette: PresentationPalette,
) -> None:
    group = _child(root, "g", id="card-grid")
    count = max(1, min(len(items), 6))
    columns = 3 if count >= 3 else count
    rows = 2 if count > 3 else 1
    gap = 18
    available_width = 1156
    card_width = (available_width - gap * (columns - 1)) // columns
    card_height = 198 if rows == 2 else 310
    start_y = 196 if rows == 2 else 230

    for index, item in enumerate(items[:6]):
        column = index % columns
        row = index // columns
        x = 62 + column * (card_width + gap)
        y = start_y + row * (card_height + gap)
        card = _child(group, "g", id=f"card-{index + 1}")
        _child(
            card,
            "rect",
            x=x,
            y=y,
            width=card_width,
            height=card_height,
            rx=6,
            fill=f"#{palette.surface}",
            stroke=f"#{palette.primary if index % 3 == 0 else palette.muted}",
            stroke_opacity="0.6",
            stroke_width=2,
        )
        _child(
            card,
            "rect",
            x=x,
            y=y,
            width=card_width,
            height=10,
            fill=f"#{[palette.primary, palette.secondary, palette.accent][index % 3]}",
        )
        _text(
            card,
            f"{index + 1:02d}",
            x=x + 24,
            y=y + 52,
            size=22,
            color=[palette.primary, palette.secondary, palette.accent][index % 3],
            weight=900,
        )

        lines = wrap_display_text(
            item,
            max_width=max(22, int(card_width / 13)),
            max_lines=5 if rows == 1 else 4,
        )
        for line_index, line in enumerate(lines):
            _text(
                card,
                line,
                x=x + 24,
                y=y + 96 + line_index * 30,
                size=19 if rows == 1 else 17,
                color=palette.text,
                weight=600,
            )


def _numbered_list(
    root,
    *,
    items: list[str],
    palette: PresentationPalette,
) -> None:
    group = _child(root, "g", id="numbered-list")
    start_y = 214
    row_height = min(94, int(420 / max(len(items), 1)))

    for index, item in enumerate(items[:5]):
        y = start_y + index * row_height
        row = _child(group, "g", id=f"item-{index + 1}")
        _child(
            row,
            "rect",
            x=62,
            y=y - 34,
            width=68,
            height=58,
            rx=4,
            fill=f"#{[palette.primary, palette.secondary, palette.accent][index % 3]}",
        )
        _text(
            row,
            f"{index + 1:02d}",
            x=96,
            y=y + 5,
            size=22,
            color=palette.background,
            weight=900,
            anchor="middle",
        )
        lines = wrap_display_text(
            item,
            max_width=78,
            max_lines=2,
        )
        for line_index, line in enumerate(lines):
            _text(
                row,
                line,
                x=160,
                y=y - 6 + line_index * 28,
                size=20,
                color=palette.text,
                weight=600,
            )
        _child(
            row,
            "line",
            x1=160,
            y1=y + 32,
            x2=1218,
            y2=y + 32,
            stroke=f"#{palette.muted}",
            stroke_opacity="0.25",
            stroke_width=1,
        )


def _content_slide(
    root,
    *,
    plan: PresentationPlan,
    slide: PresentationSlide,
    palette: PresentationPalette,
) -> None:
    _header(root, slide=slide, palette=palette)
    items = _slide_items(slide)

    if not items:
        items = [slide.subtitle or slide.title]

    if slide.index % 2 == 0 or len(items) >= 5:
        _card_grid(root, items=items, palette=palette)
    else:
        _numbered_list(root, items=items, palette=palette)

    _footer(root, plan=plan, slide=slide, palette=palette)


def render_plan_to_svg(
    plan: PresentationPlan,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    palette = get_palette(plan.style)
    paths: list[Path] = []

    for slide in plan.slides:
        root = _svg_element(
            "svg",
            {
                "viewBox": "0 0 1280 720",
                "width": 1280,
                "height": 720,
            },
        )
        _background(root, palette)

        if slide.type == "title" or slide.index == 1:
            _title_slide(
                root,
                plan=plan,
                slide=slide,
                palette=palette,
            )
            _footer(root, plan=plan, slide=slide, palette=palette)
        else:
            _content_slide(
                root,
                plan=plan,
                slide=slide,
                palette=palette,
            )

        path = output_dir / f"{slide.index:02d}_slide.svg"
        tree = ET.ElementTree(root)
        tree.write(
            path,
            encoding="utf-8",
            xml_declaration=True,
        )
        paths.append(path)

    return paths
