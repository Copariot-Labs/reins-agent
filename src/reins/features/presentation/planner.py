from __future__ import annotations

import re

from typing import Any

from reins.features.artifacts.hermes_writer import (
    HermesArtifactError,
    run_hermes_for_artifact,
)
from reins.features.presentation.models import (
    PresentationPlan,
    PresentationRequest,
    PresentationSlide,
    SlideElement,
    SlideElementType,
    SlideLayout,
)


class PresentationPlanningError(ValueError):
    pass


DEFAULT_SECTION_TITLES = [
    "Context and Opportunity",
    "Current Challenges",
    "Core Insight",
    "Proposed Direction",
    "How It Works",
    "Key Capabilities",
    "Expected Impact",
    "Implementation Plan",
    "Risks and Responses",
    "Roadmap",
    "Success Measures",
    "Next Steps",
]


def create_presentation_plan(
    request: PresentationRequest,
) -> PresentationPlan:
    if request.metadata.get("skip_ai"):
        return create_basic_plan(request)

    try:
        payload = run_hermes_for_artifact(
            prompt=_planning_prompt(request),
            artifact_format="pptx",
            timeout=int(request.metadata.get("planner_timeout", 180)),
        )
        return plan_from_model_payload(request, payload)
    except (HermesArtifactError, ValueError, TypeError) as exc:
        plan = create_basic_plan(request)
        plan.metadata.update(
            {
                "planner": "basic_fallback",
                "planning_warning": (
                    "The local presentation model was unavailable; "
                    "a deterministic outline was used instead."
                ),
                "planning_error": str(exc),
            }
        )
        return plan


def _planning_prompt(request: PresentationRequest) -> str:
    audience = request.audience or "the audience implied by the request"

    return f"""
Create a complete presentation plan from the request below.

Presentation brief:
{request.prompt}

Requirements:
- Write in {request.language}.
- Create exactly {request.slide_count} slides.
- The first slide is a concise title slide with an empty bullets list.
- The final slide closes with specific decisions, actions, or takeaways.
- Every content slide has 3-5 concrete, non-repetitive bullets.
- Use evidence and details from the brief. Never emit placeholder text.
- Audience: {audience}.
- Visual tone: {request.style.value}.
- Keep bullet text concise enough to fit on a presentation slide.
""".strip()


def plan_from_model_payload(
    request: PresentationRequest,
    payload: dict[str, Any],
) -> PresentationPlan:
    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list) or not raw_slides:
        raise PresentationPlanningError(
            "The presentation model did not return any slides."
        )

    title = _clean_text(payload.get("title")) or request.title
    title = title or derive_title(request.prompt or "")
    normalized: list[tuple[str, list[str], str]] = []

    for item in raw_slides:
        if not isinstance(item, dict):
            continue

        slide_title = _clean_text(item.get("title"))
        if not slide_title:
            continue

        raw_bullets = item.get("bullets")
        bullets = []
        if isinstance(raw_bullets, list):
            bullets = [
                cleaned
                for bullet in raw_bullets
                if (cleaned := _clean_text(bullet))
            ][:6]

        notes = _clean_text(item.get("notes"))
        normalized.append((slide_title, bullets, notes))

    if not normalized:
        raise PresentationPlanningError(
            "The presentation model returned no usable slides."
        )

    first_title, first_bullets, _ = normalized[0]
    if first_bullets or first_title.casefold() != title.casefold():
        normalized.insert(0, (title, [], ""))
    else:
        normalized[0] = (title, [], normalized[0][2])

    fallback = create_basic_plan(request)
    fallback_rows = [
        (
            slide.title,
            _items_from_slide(slide),
            slide.speaker_notes,
        )
        for slide in fallback.slides
    ]

    for fallback_row in fallback_rows:
        if len(normalized) >= request.slide_count:
            break
        if fallback_row[0].casefold() not in {
            row[0].casefold() for row in normalized
        }:
            normalized.append(fallback_row)

    normalized = normalized[: request.slide_count]

    while len(normalized) < request.slide_count:
        index = len(normalized)
        normalized.append(
            (
                f"Next Step {index}",
                [
                    "Confirm ownership and timing",
                    "Validate the decision with the target audience",
                    "Measure progress against the agreed outcome",
                ],
                "",
            )
        )

    slides = [
        _build_slide(
            index=index,
            title=slide_title,
            bullets=bullets,
            notes=notes,
            total=request.slide_count,
            audience=request.audience,
        )
        for index, (slide_title, bullets, notes) in enumerate(
            normalized,
            start=1,
        )
    ]

    return PresentationPlan(
        title=title,
        subtitle=request.audience,
        audience=request.audience,
        language=request.language,
        style=request.style,
        aspect_ratio=request.aspect_ratio,
        slides=slides,
        metadata={
            "planner": "ollama",
            "source_prompt": request.prompt or "",
        },
    )


def create_basic_plan(
    request: PresentationRequest,
) -> PresentationPlan:
    prompt = (request.prompt or "").strip()

    if not prompt:
        raise PresentationPlanningError(
            "A prompt is required to create a new presentation."
        )

    title = request.title or derive_title(prompt)
    fragments = _extract_fragments(prompt)
    slides: list[PresentationSlide] = [
        _build_slide(
            index=1,
            title=title,
            bullets=[],
            notes="",
            total=request.slide_count,
            audience=request.audience,
        )
    ]

    content_count = max(request.slide_count - 2, 0)
    section_titles = create_section_titles(
        prompt=prompt,
        count=content_count,
    )

    for offset, section_title in enumerate(section_titles, start=2):
        bullets = _fallback_bullets(
            prompt=prompt,
            fragments=fragments,
            section_title=section_title,
            offset=offset,
            audience=request.audience,
        )
        slides.append(
            _build_slide(
                index=offset,
                title=section_title,
                bullets=bullets,
                notes="",
                total=request.slide_count,
                audience=request.audience,
            )
        )

    if request.slide_count > 1:
        slides.append(
            _build_slide(
                index=request.slide_count,
                title="Decisions and Next Steps",
                bullets=[
                    "Confirm the intended outcome and decision owner",
                    "Validate the proposed direction with the target audience",
                    "Turn the agreed priorities into a dated action plan",
                ],
                notes="Close by confirming ownership, timing, and the next decision.",
                total=request.slide_count,
                audience=request.audience,
            )
        )

    return PresentationPlan(
        title=title,
        subtitle=request.audience,
        audience=request.audience,
        language=request.language,
        style=request.style,
        aspect_ratio=request.aspect_ratio,
        slides=slides,
        metadata={
            "planner": "basic",
            "source_prompt": prompt,
        },
    )


def _build_slide(
    *,
    index: int,
    title: str,
    bullets: list[str],
    notes: str,
    total: int,
    audience: str | None,
) -> PresentationSlide:
    if index == 1:
        return PresentationSlide(
            index=index,
            type="title",
            title=title,
            subtitle=audience,
            speaker_notes=notes,
            layout=SlideLayout(
                name="hero",
                columns=1,
                emphasis="title",
            ),
        )

    is_closing = index == total
    element_type = (
        SlideElementType.CARDS
        if len(bullets) in {3, 4, 6} and index % 2 == 0
        else SlideElementType.BULLETS
    )

    return PresentationSlide(
        index=index,
        type="conclusion" if is_closing else "content",
        title=title,
        elements=[
            SlideElement(
                type=element_type,
                items=bullets[:6],
            )
        ],
        speaker_notes=notes or "\n".join(bullets),
        layout=SlideLayout(
            name="closing" if is_closing else "content",
            columns=3 if element_type == SlideElementType.CARDS else 1,
            emphasis="summary" if is_closing else None,
        ),
    )


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _extract_fragments(prompt: str) -> list[str]:
    fragments = [
        _clean_text(value).lstrip("-*• ")
        for value in re.split(r"[\n\r]+|(?<=[.!?。！？；;])\s*", prompt)
    ]
    return [fragment for fragment in fragments if len(fragment) >= 4][:30]


def _fallback_bullets(
    *,
    prompt: str,
    fragments: list[str],
    section_title: str,
    offset: int,
    audience: str | None,
) -> list[str]:
    if len(fragments) >= 3:
        start = ((offset - 2) * 2) % len(fragments)
        selected = [
            fragments[(start + index) % len(fragments)]
            for index in range(min(3, len(fragments)))
        ]
        return selected

    summary = derive_title(prompt)
    audience_text = audience or "the intended audience"
    return [
        f"Frame {section_title.lower()} around: {summary}",
        f"Connect the message to the priorities of {audience_text}",
        "Make the decision, owner, evidence, and timing explicit",
    ]


def _items_from_slide(slide: PresentationSlide) -> list[str]:
    items: list[str] = []
    for element in slide.elements:
        if element.text:
            items.append(element.text)
        items.extend(element.items)
    return items


def derive_title(prompt: str) -> str:
    cleaned = " ".join(prompt.split())
    first_sentence = re.split(r"[.!?。！？\n]", cleaned, maxsplit=1)[0]
    candidate = first_sentence.strip(" -:：") or cleaned

    if len(candidate) <= 72:
        return candidate

    return candidate[:69].rstrip() + "..."


def create_section_titles(
    *,
    prompt: str,
    count: int,
) -> list[str]:
    headings = []
    for line in prompt.splitlines():
        cleaned = _clean_text(line).lstrip("#-*• ")
        if 4 <= len(cleaned) <= 72:
            headings.append(cleaned.rstrip(":："))

    unique_headings = list(dict.fromkeys(headings))
    titles = unique_headings[:count]

    for default_title in DEFAULT_SECTION_TITLES:
        if len(titles) >= count:
            break
        if default_title not in titles:
            titles.append(default_title)

    while len(titles) < count:
        titles.append(f"Additional Insight {len(titles) + 1}")

    return titles
