from __future__ import annotations

import html
import json

from pathlib import Path

from reins.features.presentation.config import PRESENTATION_CONFIG
from reins.features.presentation.engines.base import (
    EngineHealth,
    PresentationEngineAdapter,
)
from reins.features.presentation.engines.utils import directory_has_content
from reins.features.presentation.engines.visuals import get_palette, slugify
from reins.features.presentation.models import (
    PresentationArtifact,
    PresentationEngine,
    PresentationOutputFormat,
    PresentationPlan,
    PresentationRequest,
    PresentationResult,
    PresentationSlide,
)


class FrontendSlidesEngine(PresentationEngineAdapter):
    name = PresentationEngine.FRONTEND_SLIDES

    def __init__(
        self,
        engine_path: Path | None = None,
        venv_path: Path | None = None,
    ) -> None:
        config = PRESENTATION_CONFIG["frontend_slides"]
        self.engine_path = Path(
            engine_path or config["path"]
        ).expanduser().resolve()

    def health(self) -> EngineHealth:
        if not self.engine_path.exists():
            return EngineHealth(
                name=self.name,
                available=False,
                message=(
                    "Frontend Slides directory does not exist: "
                    f"{self.engine_path}"
                ),
                engine_path=self.engine_path,
            )

        if not directory_has_content(self.engine_path):
            return EngineHealth(
                name=self.name,
                available=False,
                message=(
                    "Frontend Slides directory is empty: "
                    f"{self.engine_path}"
                ),
                engine_path=self.engine_path,
            )

        skill_path = self.engine_path / "SKILL.md"
        template_path = self.engine_path / "html-template.md"

        if not skill_path.is_file() or not template_path.is_file():
            return EngineHealth(
                name=self.name,
                available=False,
                message=(
                    "Frontend Slides was found, but its skill contract "
                    "is incomplete."
                ),
                engine_path=self.engine_path,
            )

        return EngineHealth(
            name=self.name,
            available=True,
            message="Frontend Slides skill contract is available.",
            engine_path=self.engine_path,
        )

    def render(
        self,
        *,
        request: PresentationRequest,
        plan: PresentationPlan,
        workspace: Path,
    ) -> PresentationResult:
        if request.output_format != PresentationOutputFormat.HTML:
            raise ValueError("frontend_slides currently supports HTML output.")

        health = self.health()
        if not health.available:
            raise RuntimeError(health.message)

        output_dir = workspace / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{slugify(plan.title)}.html"
        output_path.write_text(
            render_plan_to_html(plan),
            encoding="utf-8",
        )

        return PresentationResult(
            success=True,
            action=request.action,
            engine=self.name,
            primary_output=output_path,
            artifacts=[
                PresentationArtifact(
                    kind="web-presentation",
                    path=output_path,
                    mime_type="text/html",
                    metadata={
                        "slide_count": len(plan.slides),
                        "self_contained": True,
                    },
                )
            ],
        )


def _slide_items(slide: PresentationSlide) -> list[str]:
    items: list[str] = []
    for element in slide.elements:
        if element.text:
            items.append(element.text)
        items.extend(element.items)
    values = [item for item in items if item.strip()]
    return values if slide.metadata.get("preserve_all_text") else values[:6]


def _render_slide(
    slide: PresentationSlide,
    *,
    title: str,
    slide_count: int,
) -> str:
    safe_title = html.escape(slide.title)
    safe_deck_title = html.escape(title)
    items = _slide_items(slide)

    if slide.type == "title":
        subtitle = html.escape(slide.subtitle or "")
        return f"""
        <section class="slide title-slide" aria-label="Slide {slide.index}: {safe_title}">
          <div class="rail"></div>
          <p class="eyebrow">REINS PRESENTATION</p>
          <h1>{safe_title}</h1>
          <p class="subtitle">{subtitle}</p>
          <div class="title-rule"><span></span><span></span><span></span></div>
          <aside class="brief-panel">
            <span class="brief-label">BRIEF</span>
            <strong>{slide_count}</strong>
            <span>SLIDES</span>
          </aside>
          <footer><span>{safe_deck_title}</span><span>{slide.index:02d} / {slide_count:02d}</span></footer>
        </section>
        """

    item_markup = "".join(
        f"""
        <article class="content-item">
          <span class="item-index">{index:02d}</span>
          <p>{html.escape(item)}</p>
        </article>
        """
        for index, item in enumerate(items or [slide.subtitle or slide.title], start=1)
    )
    if len(items) > 10:
        layout_class = "list-layout dense-layout"
    else:
        layout_class = "grid-layout" if slide.index % 2 == 0 or len(items) >= 5 else "list-layout"
    return f"""
    <section class="slide content-slide" aria-label="Slide {slide.index}: {safe_title}">
      <div class="rail"></div>
      <header>
        <p class="eyebrow">SECTION {slide.index:02d}</p>
        <h2>{safe_title}</h2>
      </header>
      <div class="content-items {layout_class}">{item_markup}</div>
      <footer><span>{safe_deck_title}</span><span>{slide.index:02d} / {slide_count:02d}</span></footer>
    </section>
    """


def render_plan_to_html(plan: PresentationPlan) -> str:
    palette = get_palette(plan.style)
    stage_width = 1280
    stage_height = 960 if plan.aspect_ratio == "4:3" else 720
    print_width = "10in" if plan.aspect_ratio == "4:3" else "13.333in"
    slides_markup = "\n".join(
        _render_slide(
            slide,
            title=plan.title,
            slide_count=len(plan.slides),
        )
        for slide in plan.slides
    )
    metadata = json.dumps(
        {
            "title": plan.title,
            "slideCount": len(plan.slides),
            "style": plan.style.value,
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="{html.escape(plan.language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{html.escape(plan.title)}</title>
  <style>
    :root {{
      --background: #{palette.background};
      --surface: #{palette.surface};
      --text: #{palette.text};
      --muted: #{palette.muted};
      --primary: #{palette.primary};
      --accent: #{palette.accent};
      --secondary: #{palette.secondary};
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden; }}
    body {{
      background: #090b0d;
      color: var(--text);
      font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
    }}
    button {{ font: inherit; }}
    .deck {{ position: fixed; inset: 0; display: grid; place-items: center; }}
    .stage {{
      position: relative;
      width: {stage_width}px;
      height: {stage_height}px;
      transform-origin: center;
      overflow: hidden;
      background: var(--background);
      box-shadow: 0 22px 70px rgba(0, 0, 0, .36);
    }}
    .slide {{
      position: absolute;
      inset: 0;
      display: none;
      padding: 54px 62px 42px 76px;
      overflow: hidden;
      background: var(--background);
    }}
    .slide.active {{ display: block; }}
    .rail {{ position: absolute; inset: 0 auto 0 0; width: 18px; background: var(--accent); }}
    .eyebrow {{ margin: 0; color: var(--accent); font-size: 14px; font-weight: 800; letter-spacing: 2px; }}
    h1, h2 {{ margin: 0; letter-spacing: 0; overflow-wrap: anywhere; }}
    h1 {{ width: 800px; margin-top: 86px; font-size: 64px; line-height: 1.06; }}
    h2 {{ max-width: 1100px; margin-top: 18px; font-size: 40px; line-height: 1.1; }}
    .subtitle {{ width: 760px; margin: 48px 0 0; color: var(--muted); font-size: 22px; line-height: 1.45; }}
    .title-rule {{ display: flex; gap: 10px; margin-top: 46px; height: 10px; }}
    .title-rule span:nth-child(1) {{ width: 190px; background: var(--primary); }}
    .title-rule span:nth-child(2) {{ width: 70px; background: var(--secondary); }}
    .title-rule span:nth-child(3) {{ width: 34px; background: var(--accent); }}
    .brief-panel {{
      position: absolute;
      top: 82px;
      right: 72px;
      width: 272px;
      height: 506px;
      padding: 38px;
      border: 2px solid var(--primary);
      border-radius: 6px;
      background: var(--surface);
      display: flex;
      flex-direction: column;
      align-items: flex-start;
    }}
    .brief-panel .brief-label {{ color: var(--primary); font-size: 14px; font-weight: 800; letter-spacing: 2px; }}
    .brief-panel strong {{ margin-top: 58px; font-size: 92px; line-height: .9; }}
    .brief-panel span:last-child {{ margin-top: 16px; color: var(--muted); font-size: 14px; font-weight: 700; letter-spacing: 2px; }}
    .content-items {{ margin-top: 54px; }}
    .content-items.dense-layout {{ max-height: 650px; overflow: auto; padding-right: 10px; }}
    .dense-layout .content-item {{ min-height: 56px; padding: 14px 18px; }}
    .dense-layout .content-item p {{ font-size: 15px; }}
    .grid-layout {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }}
    .grid-layout .content-item {{ min-height: 178px; }}
    .content-item {{
      position: relative;
      display: flex;
      gap: 22px;
      min-width: 0;
      padding: 24px;
      border: 1px solid color-mix(in srgb, var(--muted) 45%, transparent);
      border-top: 8px solid var(--primary);
      border-radius: 6px;
      background: var(--surface);
    }}
    .content-item:nth-child(3n + 2) {{ border-top-color: var(--secondary); }}
    .content-item:nth-child(3n) {{ border-top-color: var(--accent); }}
    .content-item p {{ margin: 0; font-size: 18px; font-weight: 650; line-height: 1.35; overflow-wrap: anywhere; }}
    .item-index {{ flex: 0 0 auto; color: var(--primary); font-size: 18px; font-weight: 900; }}
    .list-layout {{ display: grid; gap: 14px; margin-top: 46px; }}
    .list-layout .content-item {{ min-height: 74px; align-items: center; border-top-width: 1px; }}
    .list-layout .content-item p {{ font-size: 20px; }}
    footer {{
      position: absolute;
      left: 62px;
      right: 62px;
      bottom: 18px;
      display: flex;
      justify-content: space-between;
      padding-top: 12px;
      border-top: 1px solid color-mix(in srgb, var(--muted) 35%, transparent);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .controls {{
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 4;
      display: flex;
      gap: 8px;
      align-items: center;
      color: white;
    }}
    .controls button {{
      width: 40px;
      height: 40px;
      border: 1px solid rgba(255,255,255,.35);
      border-radius: 50%;
      color: white;
      background: rgba(9,11,13,.78);
      cursor: pointer;
    }}
    .controls button:focus-visible {{ outline: 3px solid var(--accent); outline-offset: 2px; }}
    .counter {{ min-width: 58px; text-align: center; font-size: 13px; font-weight: 700; }}
    @media print {{
      html, body {{ height: auto; overflow: visible; background: white; }}
      .deck, .stage {{ position: static; display: block; width: auto; height: auto; transform: none !important; box-shadow: none; }}
      .slide {{ position: relative; display: block; width: {print_width}; height: 7.5in; break-after: page; }}
      .controls {{ display: none; }}
    }}
    @media (prefers-reduced-motion: no-preference) {{
      .slide.active .content-item {{ animation: enter .35s ease both; }}
      .slide.active .content-item:nth-child(2) {{ animation-delay: .05s; }}
      .slide.active .content-item:nth-child(3) {{ animation-delay: .1s; }}
      @keyframes enter {{ from {{ opacity: 0; transform: translateY(10px); }} }}
    }}
  </style>
</head>
<body>
  <main class="deck">
    <div class="stage" id="stage">{slides_markup}</div>
  </main>
  <nav class="controls" aria-label="Presentation controls">
    <button id="previous" type="button" aria-label="Previous slide" title="Previous slide">&#8592;</button>
    <span class="counter" id="counter" aria-live="polite"></span>
    <button id="next" type="button" aria-label="Next slide" title="Next slide">&#8594;</button>
  </nav>
  <script type="application/json" id="deck-metadata">{metadata}</script>
  <script>
    (() => {{
      const stage = document.getElementById('stage');
      const slides = [...document.querySelectorAll('.slide')];
      const counter = document.getElementById('counter');
      let current = 0;
      const clamp = (value) => Math.max(0, Math.min(value, slides.length - 1));
      const render = (value) => {{
        current = clamp(value);
        slides.forEach((slide, index) => slide.classList.toggle('active', index === current));
        counter.textContent = `${{current + 1}} / ${{slides.length}}`;
        history.replaceState(null, '', `#${{current + 1}}`);
      }};
      const scale = () => {{
        const factor = Math.min(innerWidth / {stage_width}, innerHeight / {stage_height});
        stage.style.transform = `scale(${{factor}})`;
      }};
      document.getElementById('previous').addEventListener('click', () => render(current - 1));
      document.getElementById('next').addEventListener('click', () => render(current + 1));
      addEventListener('keydown', (event) => {{
        if (['ArrowRight', 'PageDown', ' '].includes(event.key)) {{ event.preventDefault(); render(current + 1); }}
        if (['ArrowLeft', 'PageUp'].includes(event.key)) {{ event.preventDefault(); render(current - 1); }}
        if (event.key === 'Home') render(0);
        if (event.key === 'End') render(slides.length - 1);
      }});
      addEventListener('resize', scale);
      scale();
      const initial = Number(location.hash.slice(1)) - 1;
      render(Number.isFinite(initial) ? initial : 0);
    }})();
  </script>
</body>
</html>
"""
