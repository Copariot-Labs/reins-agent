from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator


class PresentationAction(str, Enum):
    """
    Supported presentation operations.
    """

    NEW = "new"
    MODIFY = "modify"
    RESTYLE = "restyle"
    CONVERT = "convert"


class PresentationOutputFormat(str, Enum):
    """
    Supported presentation output formats.
    """

    PPTX = "pptx"
    HTML = "html"
    PDF = "pdf"


class PresentationEngine(str, Enum):
    """
    Presentation rendering engines.
    """

    AUTO = "auto"
    PPT_MASTER = "ppt_master"
    FRONTEND_SLIDES = "frontend_slides"
    NATIVE_PPTX = "native_pptx"


class PresentationJobStatus(str, Enum):
    """
    Lifecycle states for a presentation-generation job.
    """

    CREATED = "created"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    PLAN_READY = "plan_ready"
    RENDERING = "rendering"
    APPLYING = "applying"
    QA = "qa"
    COMPLETED = "completed"
    FAILED = "failed"


class PresentationStyle(str, Enum):
    """
    High-level presentation style presets.
    """

    MODERN = "modern"
    TECH = "tech"
    CORPORATE = "corporate"
    CREATIVE = "creative"
    MINIMAL = "minimal"
    DARK = "dark"


class SlideElementType(str, Enum):
    """
    Supported slide content element types.
    """

    TEXT = "text"
    BULLETS = "bullets"
    IMAGE = "image"
    CARDS = "cards"
    TABLE = "table"
    CHART = "chart"
    QUOTE = "quote"
    TIMELINE = "timeline"
    METRIC = "metric"


class SlideElement(BaseModel):
    """
    A reusable content element inside a slide.
    """

    type: SlideElementType
    title: str | None = None
    text: str | None = None
    items: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class SlideLayout(BaseModel):
    """
    Layout instructions shared with presentation engines.
    """

    name: str = "content"
    columns: int = Field(
        default=1,
        ge=1,
        le=12,
    )
    emphasis: str | None = None
    background: str | None = None


class PresentationSlide(BaseModel):
    """
    A normalized presentation slide.
    """

    index: int = Field(ge=1)
    type: str
    title: str
    subtitle: str | None = None
    elements: list[SlideElement] = Field(default_factory=list)
    speaker_notes: str = ""
    layout: SlideLayout = Field(default_factory=SlideLayout)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresentationPlan(BaseModel):
    """
    Structured presentation plan created before rendering.
    """

    title: str
    subtitle: str | None = None
    audience: str | None = None
    language: str = "en"
    style: PresentationStyle = PresentationStyle.MODERN
    aspect_ratio: str = "16:9"
    slides: list[PresentationSlide] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresentationRequest(BaseModel):
    """
    Input accepted by the Reins presentation service.
    """

    action: PresentationAction = PresentationAction.NEW

    prompt: str | None = Field(
        default=None,
        max_length=30_000,
    )
    source_path: Path | None = None
    instruction: str | None = Field(
        default=None,
        max_length=10_000,
    )

    title: str | None = Field(
        default=None,
        max_length=180,
    )
    audience: str | None = Field(
        default=None,
        max_length=300,
    )
    language: str = Field(
        default="en",
        min_length=2,
        max_length=20,
    )

    slide_count: int = Field(
        default=8,
        ge=1,
        le=50,
    )

    style: PresentationStyle = PresentationStyle.MODERN
    output_format: PresentationOutputFormat = (
        PresentationOutputFormat.PPTX
    )
    engine: PresentationEngine = PresentationEngine.AUTO

    aspect_ratio: str = Field(
        default="16:9",
        pattern=r"^(16:9|4:3)$",
    )
    output_path: Path | None = None

    run_qa: bool = True
    maximum_qa_rounds: int = Field(
        default=3,
        ge=0,
        le=10,
    )

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_operation_inputs(self) -> "PresentationRequest":
        if self.action == PresentationAction.NEW:
            if not (self.prompt or "").strip():
                raise ValueError(
                    "A prompt is required to create a presentation."
                )
        elif self.source_path is None:
            raise ValueError(
                f"source_path is required for {self.action.value}."
            )

        if (
            self.action == PresentationAction.MODIFY
            and not (self.instruction or "").strip()
        ):
            raise ValueError(
                "An instruction is required to modify a presentation."
            )

        return self


class PresentationArtifact(BaseModel):
    """
    A generated presentation artifact.
    """

    kind: str
    path: Path
    mime_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PresentationWorkspace(BaseModel):
    """
    Filesystem paths belonging to a presentation job.
    """

    job_id: str
    root: Path
    request_path: Path
    plan_path: Path
    status_path: Path
    output_dir: Path
    preview_dir: Path
    asset_dir: Path
    log_dir: Path


class PresentationJobState(BaseModel):
    """
    Persisted state for a presentation job.
    """

    job_id: str
    status: PresentationJobStatus = PresentationJobStatus.CREATED
    progress: int = Field(
        default=0,
        ge=0,
        le=100,
    )
    phase: str = "Presentation job created"

    action: PresentationAction
    engine: PresentationEngine = PresentationEngine.AUTO

    created_at: str
    updated_at: str

    output_path: Path | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[PresentationArtifact] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)


class PresentationResult(BaseModel):
    """
    Result returned by a presentation operation.
    """

    success: bool
    action: PresentationAction
    engine: PresentationEngine

    job_id: str | None = None
    primary_output: Path | None = None
    artifacts: list[PresentationArtifact] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
