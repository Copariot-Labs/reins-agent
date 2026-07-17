from __future__ import annotations

import subprocess

from pathlib import Path

from reins.features.presentation.config import PRESENTATION_CONFIG
from reins.features.presentation.engines.base import (
    EngineHealth,
    PresentationEngineAdapter,
)
from reins.features.presentation.engines.utils import (
    directory_has_content,
    get_venv_python,
)
from reins.features.presentation.engines.svg_renderer import (
    render_plan_to_svg,
)
from reins.features.presentation.engines.visuals import get_palette, slugify
from reins.features.presentation.models import (
    PresentationArtifact,
    PresentationEngine,
    PresentationOutputFormat,
    PresentationPlan,
    PresentationRequest,
    PresentationResult,
)


class PptMasterEngine(PresentationEngineAdapter):
    name = PresentationEngine.PPT_MASTER

    def __init__(
        self,
        engine_path: Path | None = None,
        venv_path: Path | None = None,
    ) -> None:
        config = PRESENTATION_CONFIG["ppt_master"]

        self.engine_path = Path(
            engine_path or config["path"]
        ).expanduser().resolve()

        self.venv_path = Path(
            venv_path or config["venv"]
        ).expanduser().resolve()

        self.python_path = get_venv_python(self.venv_path)

    def health(self) -> EngineHealth:
        if not self.engine_path.exists():
            return EngineHealth(
                name=self.name,
                available=False,
                message=f"PPT Master directory does not exist: {self.engine_path}",
                engine_path=self.engine_path,
                python_path=self.python_path,
            )

        if not directory_has_content(self.engine_path):
            return EngineHealth(
                name=self.name,
                available=False,
                message=f"PPT Master directory is empty: {self.engine_path}",
                engine_path=self.engine_path,
                python_path=self.python_path,
            )

        if not self.python_path.is_file():
            return EngineHealth(
                name=self.name,
                available=False,
                message=(
                    "PPT Master virtual environment Python was not found: "
                    f"{self.python_path}"
                ),
                engine_path=self.engine_path,
                python_path=self.python_path,
            )

        skill_candidates = [
            self.engine_path / "skills" / "ppt-master" / "SKILL.md",
            self.engine_path / "SKILL.md",
        ]

        if not any(path.is_file() for path in skill_candidates):
            return EngineHealth(
                name=self.name,
                available=False,
                message=(
                    "PPT Master was found, but no SKILL.md entrypoint "
                    "could be detected."
                ),
                engine_path=self.engine_path,
                python_path=self.python_path,
            )

        return EngineHealth(
            name=self.name,
            available=True,
            message="PPT Master engine and virtual environment are available.",
            engine_path=self.engine_path,
            python_path=self.python_path,
        )

    def render(
        self,
        *,
        request: PresentationRequest,
        plan: PresentationPlan,
        workspace: Path,
    ) -> PresentationResult:
        if request.output_format != PresentationOutputFormat.PPTX:
            raise ValueError("ppt_master only supports PPTX output.")

        health = self.health()
        if not health.available:
            raise RuntimeError(health.message)

        project_dir = workspace
        svg_dir = project_dir / "svg_output"
        notes_dir = project_dir / "notes"
        output_dir = project_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        notes_dir.mkdir(parents=True, exist_ok=True)

        svg_paths = render_plan_to_svg(plan, svg_dir)
        palette = get_palette(plan.style)
        (project_dir / "spec_lock.md").write_text(
            "\n".join(
                [
                    "# Execution Lock",
                    "",
                    "## canvas",
                    "- viewBox: 0 0 1280 720",
                    (
                        "- format: PPT 4:3"
                        if plan.aspect_ratio == "4:3"
                        else "- format: PPT 16:9"
                    ),
                    "",
                    "## colors",
                    f"- bg: #{palette.background}",
                    f"- bg_secondary: #{palette.surface}",
                    f"- primary: #{palette.primary}",
                    f"- accent: #{palette.accent}",
                    f"- secondary_accent: #{palette.secondary}",
                    f"- text: #{palette.text}",
                    f"- text_secondary: #{palette.muted}",
                    "",
                    "## typography",
                    (
                        '- font_family: "Microsoft YaHei", "PingFang SC", '
                        '"Noto Sans CJK SC", Arial, sans-serif'
                    ),
                    (
                        '- title_family: "Microsoft YaHei", "PingFang SC", '
                        '"Noto Sans CJK SC", Arial, sans-serif'
                    ),
                    (
                        '- body_family: "Microsoft YaHei", "PingFang SC", '
                        '"Noto Sans CJK SC", Arial, sans-serif'
                    ),
                    "- title: 38",
                    "- body: 20",
                    "- subtitle: 24",
                    "- cover_title: 60",
                    "- annotation: 13",
                    "- footnote: 12",
                    "",
                    "## forbidden",
                    "- foreignObject, script, iframe, animation elements",
                ]
            ),
            encoding="utf-8",
        )

        for slide, svg_path in zip(plan.slides, svg_paths, strict=True):
            if slide.speaker_notes:
                (notes_dir / f"{svg_path.stem}.md").write_text(
                    slide.speaker_notes,
                    encoding="utf-8",
                )

        output_path = output_dir / f"{slugify(plan.title)}.pptx"
        converter = (
            self.engine_path
            / "skills"
            / "ppt-master"
            / "scripts"
            / "svg_to_pptx.py"
        )

        if not converter.is_file():
            raise RuntimeError(
                f"PPT Master converter was not found: {converter}"
            )

        timeout = int(request.metadata.get("render_timeout", 300))
        command = [
            str(self.python_path),
            str(converter),
            str(project_dir),
            "--output",
            str(output_path),
            "--format",
            "ppt43" if plan.aspect_ratio == "4:3" else "ppt169",
            "--pptx-structure",
            "flat",
            "--transition",
            "fade",
            "--animation",
            "none",
            "--quiet",
        ]

        completed = subprocess.run(
            command,
            cwd=self.engine_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        log_path = project_dir / "logs" / "ppt-master.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "\n".join(
                [
                    f"command: {' '.join(command)}",
                    f"exit_code: {completed.returncode}",
                    "stdout:",
                    completed.stdout,
                    "stderr:",
                    completed.stderr,
                ]
            ),
            encoding="utf-8",
        )

        if completed.returncode != 0 or not output_path.is_file():
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                "PPT Master conversion failed. "
                f"{detail[-1200:] if detail else 'No output was produced.'}"
            )

        return PresentationResult(
            success=True,
            action=request.action,
            engine=self.name,
            primary_output=output_path,
            artifacts=[
                PresentationArtifact(
                    kind="presentation",
                    path=output_path,
                    mime_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "presentationml.presentation"
                    ),
                    metadata={
                        "editable": True,
                        "slide_count": len(svg_paths),
                        "renderer": "ppt-master-svg-to-drawingml",
                    },
                ),
                PresentationArtifact(
                    kind="render-log",
                    path=log_path,
                    mime_type="text/plain",
                ),
            ],
        )
