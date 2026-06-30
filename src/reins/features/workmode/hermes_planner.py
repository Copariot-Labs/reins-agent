from __future__ import annotations

from typing import Any

from reins.features.workmode.artifacts import infer_office_artifact_format
from reins.features.workmode.desktop_resolver import (
    infer_desktop_app_name,
    is_desktop_app_intent,
)
from reins.features.workmode.planner import WorkPlan, WorkStep
from reins.features.workmode.router import ExecutionPath
from reins.features.workmode.url_resolver import (
    infer_search_query_from_message,
    infer_url_from_message,
    is_browser_intent,
    is_web_search_intent,
)
from reins.features.workmode.vendor_hermes import call_vendor_hermes_planner
from reins.features.workmode.runtime.execution_contract import ExecutionContract


class HermesPlannerError(Exception):
    pass


ALLOWED_STEP_KINDS = {
    "backend_only",
    "backend_process",
    "result_present",
    "office_generate",
    "artifact_present",
    "browser_source",
    "desktop_capture",
    "ocr",
    "wechat_prepare",
    "confirmation_gate",
}


DOCUMENT_GENERATION_PHRASES = [
    "write a report",
    "create a report",
    "generate a report",
    "make a report",
    "prepare a report",
    "write report",
    "create report",
    "generate report",
    "make report",
    "prepare report",
    "write a document",
    "create a document",
    "generate a document",
    "make a document",
    "prepare a document",
    "write document",
    "create document",
    "generate document",
    "make document",
    "prepare document",
    "write an application",
    "write application",
    "create application",
    "generate application",
    "prepare application",
    "write a letter",
    "write letter",
    "create letter",
    "generate letter",
    "prepare letter",
    "write a memo",
    "create memo",
    "generate memo",
    "prepare memo",
    "write notice",
    "create notice",
    "generate notice",
    "prepare notice",
    "create spreadsheet",
    "generate spreadsheet",
    "prepare spreadsheet",
    "create workbook",
    "generate workbook",
    "prepare workbook",
    "create excel",
    "generate excel",
    "prepare excel",
    "create presentation",
    "generate presentation",
    "prepare presentation",
    "create slides",
    "generate slides",
    "prepare slides",
]


def normalize_kind(raw: dict[str, Any]) -> str:
    """
    Minimal deterministic kind normalization.

    Do not put full routing logic here.
    Reins repairs route conflicts later in _repair_steps().
    """

    kind = str(raw.get("kind") or "backend_only").strip().lower()

    if kind not in ALLOWED_STEP_KINDS:
        kind = "backend_only"

    return kind


def _make_step(raw: dict[str, Any]) -> WorkStep:
    if not isinstance(raw, dict):
        raise HermesPlannerError("Hermes step must be a JSON object.")

    kind = normalize_kind(raw)

    ExecutionContract.validate(kind)

    return WorkStep(
        id=str(raw.get("id") or kind),
        kind=kind,
        title=str(raw.get("title") or "Untitled step"),
        worker=str(raw.get("worker") or "workmode.backend"),
        description=str(raw.get("description") or ""),
        visible_action=bool(raw.get("visible_action", False)),
        requires_confirmation=bool(raw.get("requires_confirmation", False)),
        expected_artifacts=list(raw.get("expected_artifacts") or []),
        depends_on=list(raw.get("depends_on") or []),
        metadata=dict(raw.get("metadata") or {}),
    )


def _path_value(path: Any) -> str:
    return path.value if isinstance(path, ExecutionPath) else str(path)


def _is_browser_path(path: Any) -> bool:
    return path == ExecutionPath.BROWSER or _path_value(path) == ExecutionPath.BROWSER.value


def _is_desktop_path(path: Any) -> bool:
    return path == ExecutionPath.DESKTOP or _path_value(path) == ExecutionPath.DESKTOP.value


def _is_office_path(path: Any) -> bool:
    return path == ExecutionPath.OFFICE or _path_value(path) == ExecutionPath.OFFICE.value


def _step_text(step: WorkStep) -> str:
    return " ".join(
        [
            step.kind,
            step.title,
            step.worker,
            step.description,
            " ".join(str(value) for value in step.metadata.values()),
        ]
    )


def _is_document_generation_intent(message: str) -> bool:
    text = message.lower()

    if any(phrase in text for phrase in DOCUMENT_GENERATION_PHRASES):
        return True

    # Lightweight generic writing/document detection.
    return (
        ("write" in text or "create" in text or "generate" in text or "prepare" in text or "make" in text)
        and (
            "report" in text
            or "document" in text
            or "application" in text
            or "letter" in text
            or "memo" in text
            or "notice" in text
            or "docx" in text
            or "xlsx" in text
            or "pptx" in text
            or "word" in text
            or "excel" in text
            or "spreadsheet" in text
            or "workbook" in text
            or "powerpoint" in text
            or "presentation" in text
            or "slides" in text
        )
    )


def _visible_office_presentation(policy: Any) -> bool:
    return bool(
        getattr(policy, "visible_actions", False)
        and getattr(policy, "show_office_windows", False)
    )


def _repair_office_steps(
    steps: list[WorkStep],
    *,
    message: str,
    policy: Any,
) -> list[WorkStep]:
    """
    If any plan contains office_generate, it must also contain artifact_present.

    This fixes:
    - Hermes path says backend_only but step kind is office_generate
    - Office file generated but not opened/presented in work mode
    """

    has_office_generate = any(step.kind == "office_generate" for step in steps)

    if not has_office_generate:
        return steps

    repaired: list[WorkStep] = []

    for step in steps:
        if step.kind == "office_generate":
            artifact_format = infer_office_artifact_format(
                message,
                step.metadata,
                step.expected_artifacts,
                step.title,
                step.description,
            )
            metadata = dict(step.metadata)
            metadata.setdefault("artifact_format", artifact_format)
            repaired.append(
                WorkStep(
                    id=step.id,
                    kind="office_generate",
                    title=step.title or "Generate Office artifact",
                    worker="workmode.office",
                    description=step.description or "Generate the requested Office document in the backend.",
                    visible_action=False,
                    requires_confirmation=False,
                    expected_artifacts=step.expected_artifacts or [artifact_format],
                    depends_on=step.depends_on,
                    metadata=metadata,
                )
            )
            continue

        # Rebuild one canonical artifact_present step.
        if step.kind == "artifact_present":
            continue

        repaired.append(step)

    last_office_step = next(
        step for step in reversed(repaired)
        if step.kind == "office_generate"
    )
    artifact_format = infer_office_artifact_format(
        message,
        last_office_step.metadata,
        last_office_step.expected_artifacts,
        last_office_step.title,
        last_office_step.description,
    )

    should_show = _visible_office_presentation(policy)

    repaired.append(
        WorkStep(
            id=f"{last_office_step.id}-present",
            kind="artifact_present",
            title=(
                "Present generated Office artifact"
                if should_show
                else "Record generated Office artifact"
            ),
            worker="workmode.presenter",
            description=(
                "Open the generated Office artifact for operator verification."
                if should_show
                else "Record the generated Office artifact path without opening desktop windows."
            ),
            visible_action=should_show,
            requires_confirmation=False,
            expected_artifacts=[],
            depends_on=[last_office_step.id],
            metadata={
                "artifact_kind": artifact_format,
            },
        )
    )

    return repaired


def _repair_desktop_steps(
    steps: list[WorkStep],
    *,
    message: str,
    policy: Any,
) -> list[WorkStep]:
    app_name = infer_desktop_app_name(message)

    for step in steps:
        if step.kind == "desktop_capture":
            metadata = dict(step.metadata)

            if app_name and not metadata.get("app_name"):
                metadata["app_name"] = app_name

            return [
                WorkStep(
                    id=step.id,
                    kind="desktop_capture",
                    title=step.title or "Capture desktop evidence",
                    worker="workmode.desktop",
                    description=step.description
                    or "Open or capture desktop evidence for operator verification.",
                    visible_action=bool(getattr(policy, "visible_actions", False)),
                    requires_confirmation=False,
                    expected_artifacts=step.expected_artifacts or ["screenshot"],
                    depends_on=step.depends_on,
                    metadata=metadata,
                )
            ]

    return [
        WorkStep(
            id="desktop-capture",
            kind="desktop_capture",
            title=f"Open {app_name} and capture proof" if app_name else "Capture desktop evidence",
            worker="workmode.desktop",
            description="Open or capture the requested desktop state for operator verification.",
            visible_action=bool(getattr(policy, "visible_actions", False)),
            requires_confirmation=False,
            expected_artifacts=["screenshot"],
            depends_on=[],
            metadata={"app_name": app_name} if app_name else {},
        )
    ]


def _repair_browser_steps(
    steps: list[WorkStep],
    *,
    message: str,
    policy: Any,
) -> list[WorkStep]:
    search_intent = is_web_search_intent(message)
    url = infer_url_from_message(message)

    for step in steps:
        if step.kind == "browser_source":
            metadata = dict(step.metadata)

            if search_intent:
                metadata["research"] = True
                metadata.setdefault("query", infer_search_query_from_message(message))
                metadata.setdefault("max_sources", 3)
            elif url and not metadata.get("url"):
                metadata["url"] = url

            return [
                WorkStep(
                    id=step.id,
                    kind="browser_source",
                    title=step.title or ("Research web sources" if search_intent else "Open browser evidence"),
                    worker="workmode.browser",
                    description=step.description
                    or (
                        "Search, open source pages, and save browser research proof."
                        if search_intent
                        else "Open a browser source for operator verification."
                    ),
                    visible_action=bool(getattr(policy, "visible_actions", False)),
                    requires_confirmation=False,
                    expected_artifacts=step.expected_artifacts,
                    depends_on=step.depends_on,
                    metadata=metadata,
                )
            ]

    return [
        WorkStep(
            id="browser-source",
            kind="browser_source",
            title="Research web sources" if search_intent else "Open browser evidence",
            worker="workmode.browser",
            description=(
                "Search, open source pages, and save browser research proof."
                if search_intent
                else "Open the requested website and save browser evidence for verification."
            ),
            visible_action=bool(getattr(policy, "visible_actions", False)),
            requires_confirmation=False,
            expected_artifacts=[],
            depends_on=[],
            metadata=(
                {
                    "research": True,
                    "query": infer_search_query_from_message(message),
                    "max_sources": 3,
                }
                if search_intent
                else ({"url": url} if url else {})
            ),
        )
    ]


def _repair_browser_document_chain(
    steps: list[WorkStep],
    *,
    message: str,
    policy: Any,
) -> list[WorkStep]:
    """
    Mixed request:
        visit website and write report

    Correct chain:
        browser_source -> office_generate -> artifact_present
    """

    browser_steps = _repair_browser_steps(
        steps,
        message=message,
        policy=policy,
    )

    browser_step_id = browser_steps[-1].id

    existing_office_steps = [step for step in steps if step.kind == "office_generate"]

    if existing_office_steps:
        office_seed_steps: list[WorkStep] = []

        for step in existing_office_steps:
            artifact_format = infer_office_artifact_format(
                message,
                step.metadata,
                step.expected_artifacts,
                step.title,
                step.description,
            )
            office_seed_steps.append(
                WorkStep(
                    id=step.id,
                    kind="office_generate",
                    title=step.title or "Generate document from browser evidence",
                    worker="workmode.office",
                    description=step.description
                    or "Generate the requested document using browser evidence and source context.",
                    visible_action=False,
                    requires_confirmation=False,
                    expected_artifacts=step.expected_artifacts or [artifact_format],
                    depends_on=step.depends_on or [browser_step_id],
                    metadata={
                        **dict(step.metadata),
                        "artifact_format": artifact_format,
                        "source": "browser_context",
                        "document_instruction": message,
                    },
                )
            )
    else:
        artifact_format = infer_office_artifact_format(message)
        office_seed_steps = [
            WorkStep(
                id="office-generate",
                kind="office_generate",
                title="Generate document from browser evidence",
                worker="workmode.office",
                description="Generate the requested document using browser evidence and source context.",
                visible_action=False,
                requires_confirmation=False,
                expected_artifacts=[artifact_format],
                depends_on=[browser_step_id],
                metadata={
                    "artifact_format": artifact_format,
                    "source": "browser_context",
                    "document_instruction": message,
                },
            )
        ]

    office_steps = _repair_office_steps(
        office_seed_steps,
        message=message,
        policy=policy,
    )

    return browser_steps + office_steps


def _repair_steps(
    steps: list[WorkStep],
    *,
    message: str,
    policy: Any,
    path: Any,
) -> list[WorkStep]:
    """
    Hermes plans, Reins repairs.

    Reins owns:
    - worker compatibility
    - route safety
    - artifact presentation
    - mixed browser -> office chains
    """

    has_office_generate = any(step.kind == "office_generate" for step in steps)

    should_be_browser = _is_browser_path(path) or is_browser_intent(message) or any(
        is_browser_intent(_step_text(step)) for step in steps
    )

    should_generate_document = _is_document_generation_intent(message) or has_office_generate

    # Mixed browser + document generation:
    # visit website/search web + write/generate report/document
    if should_be_browser and should_generate_document:
        return _repair_browser_document_chain(
            steps,
            message=message,
            policy=policy,
        )

    # Office repair must trigger even if path is backend_only but Hermes emitted office_generate.
    if _is_office_path(path) or has_office_generate:
        return _repair_office_steps(steps, message=message, policy=policy)

    if should_be_browser:
        return _repair_browser_steps(
            steps,
            message=message,
            policy=policy,
        )

    should_be_desktop = _is_desktop_path(path) or is_desktop_app_intent(message) or any(
        is_desktop_app_intent(_step_text(step)) for step in steps
    )

    if should_be_desktop:
        return _repair_desktop_steps(
            steps,
            message=message,
            policy=policy,
        )

    return steps


def _validate_plan_dict(raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        raise HermesPlannerError("Hermes planner output is not a JSON object.")

    steps = raw.get("steps")

    if not isinstance(steps, list) or not steps:
        raise HermesPlannerError("Hermes planner steps must be a non-empty list.")

    for step in steps:
        if not isinstance(step, dict):
            raise HermesPlannerError("Each Hermes step must be a JSON object.")


def build_plan_from_hermes_dict(
    raw: dict[str, Any],
    *,
    message: str,
    policy: Any,
    path: Any,
) -> WorkPlan:
    _validate_plan_dict(raw)

    raw_steps = [_make_step(step) for step in raw["steps"]]

    steps = _repair_steps(
        raw_steps,
        message=message,
        policy=policy,
        path=path,
    )

    return WorkPlan(
        id=str(raw.get("id") or raw.get("plan_id") or "hermes-plan"),
        intent=str(raw.get("intent") or message),
        execution_path=_path_value(path),
        mode=policy.mode,
        summary_for_user=str(
            raw.get("summary_for_user")
            or "Hermes generated a WorkMode plan."
        ),
        steps=steps,
        risk_flags=list(raw.get("risk_flags") or []),
        planner="hermes",
        version=int(raw.get("version") or 1),
    )


def try_build_hermes_plan(
    message: str,
    *,
    policy: Any,
    path: Any,
    intake: dict[str, Any] | None = None,
) -> tuple[WorkPlan | None, dict[str, Any] | None]:
    try:
        raw = call_vendor_hermes_planner(
            message,
            mode=policy.mode,
            intake=intake,
        )

        plan = build_plan_from_hermes_dict(
            raw,
            message=message,
            policy=policy,
            path=path,
        )

        return plan, None

    except Exception as exc:
        return None, {
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
