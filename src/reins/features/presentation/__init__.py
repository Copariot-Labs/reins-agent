"""
Reins Presentation Feature.

Provides presentation creation, editing, conversion,
restyling, rendering, storage, and quality-assurance workflows.
"""

from .models import (
    PresentationAction,
    PresentationArtifact,
    PresentationEngine,
    PresentationJobState,
    PresentationJobStatus,
    PresentationOutputFormat,
    PresentationPlan,
    PresentationRequest,
    PresentationResult,
    PresentationSlide,
    PresentationStyle,
    PresentationWorkspace,
    SlideElement,
    SlideElementType,
    SlideLayout,
)

FEATURE_NAME = "presentation"
FEATURE_VERSION = "0.1.0"

__all__ = [
    "FEATURE_NAME",
    "FEATURE_VERSION",
    "PresentationAction",
    "PresentationArtifact",
    "PresentationEngine",
    "PresentationJobState",
    "PresentationJobStatus",
    "PresentationOutputFormat",
    "PresentationPlan",
    "PresentationRequest",
    "PresentationResult",
    "PresentationSlide",
    "PresentationStyle",
    "PresentationWorkspace",
    "SlideElement",
    "SlideElementType",
    "SlideLayout",
]