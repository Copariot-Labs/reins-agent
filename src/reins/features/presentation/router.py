from __future__ import annotations

from reins.features.presentation.models import (
    PresentationAction,
    PresentationEngine,
    PresentationOutputFormat,
    PresentationRequest,
)


class PresentationRoutingError(ValueError):
    pass


def select_presentation_engine(
    request: PresentationRequest,
) -> PresentationEngine:
    if request.engine != PresentationEngine.AUTO:
        validate_explicit_engine(request)
        return request.engine

    if (
        request.output_format
        == PresentationOutputFormat.HTML
    ):
        return PresentationEngine.FRONTEND_SLIDES

    if request.action == PresentationAction.CONVERT:
        if request.output_format == PresentationOutputFormat.HTML:
            return PresentationEngine.FRONTEND_SLIDES
        if request.output_format == PresentationOutputFormat.PDF:
            return PresentationEngine.NATIVE_PPTX

    if request.action in {
        PresentationAction.MODIFY,
        PresentationAction.RESTYLE,
    }:
        return PresentationEngine.NATIVE_PPTX

    if request.action == PresentationAction.NEW:
        return PresentationEngine.PPT_MASTER

    raise PresentationRoutingError(
        "No compatible engine could be selected for "
        f"action={request.action.value!r}, "
        f"output_format={request.output_format.value!r}."
    )


def validate_explicit_engine(
    request: PresentationRequest,
) -> None:
    if (
        request.engine
        == PresentationEngine.FRONTEND_SLIDES
        and request.output_format
        == PresentationOutputFormat.PPTX
    ):
        raise PresentationRoutingError(
            "Frontend Slides cannot create an editable "
            "PPTX output. Use ppt_master instead."
        )

    if (
        request.engine
        == PresentationEngine.NATIVE_PPTX
        and request.output_format
        != PresentationOutputFormat.PPTX
    ):
        raise PresentationRoutingError(
            "native_pptx only supports PPTX output."
        )

    if (
        request.engine
        == PresentationEngine.PPT_MASTER
        and request.output_format
        == PresentationOutputFormat.HTML
    ):
        raise PresentationRoutingError(
            "ppt_master does not produce HTML presentations. "
            "Use frontend_slides instead."
        )
