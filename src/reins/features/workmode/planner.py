from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from reins.features.workmode.artifacts import infer_office_artifact_format
from reins.features.workmode.desktop_resolver import infer_desktop_app_name
from reins.features.workmode.policy import ModePolicy
from reins.features.workmode.router import ExecutionPath
from reins.features.workmode.url_resolver import (
    infer_search_query_from_message,
    infer_url_from_message,
    is_web_search_intent,
)


@dataclass(frozen=True)
class WorkStep:
    id: str
    kind: str
    title: str
    worker: str
    description: str
    visible_action: bool = False
    requires_confirmation: bool = False
    expected_artifacts: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class WorkPlan:
    id: str
    intent: str
    execution_path: str
    mode: str
    summary_for_user: str
    steps: list[WorkStep]
    risk_flags: list[str] = field(default_factory=list)
    planner: str = "fallback_router"
    version: int = 1

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["step_count"] = len(self.steps)
        return data


def build_fallback_plan(message: str, *, policy: ModePolicy, path: ExecutionPath) -> WorkPlan:
    steps = _build_steps(message, policy=policy, path=path)
    risk_flags = []

    if any(step.requires_confirmation for step in steps):
        risk_flags.append("confirmation_required")

    if not policy.visible_actions:
        risk_flags.append("headless_no_visible_actions")

    return WorkPlan(
        id=str(uuid4()),
        intent=message,
        execution_path=path.value,
        mode=policy.mode,
        summary_for_user=_summary_for_path(path, policy=policy),
        steps=steps,
        risk_flags=risk_flags,
    )


def _build_steps(message: str, *, policy: ModePolicy, path: ExecutionPath) -> list[WorkStep]:
    visible_action = policy.visible_actions and path in {
        ExecutionPath.BACKEND_WITH_PRESENTATION,
        ExecutionPath.BROWSER,
        ExecutionPath.DESKTOP,
        ExecutionPath.OFFICE,
        ExecutionPath.WECHAT,
    }

    if path == ExecutionPath.OFFICE:
        artifact_format = infer_office_artifact_format(message)
        present_title = "Present Office artifact" if visible_action else "Record Office artifact"
        present_description = (
            "Open the generated document for operator verification."
            if visible_action
            else "Record the generated document path without opening desktop windows."
        )

        return [
            WorkStep(
                id="office-generate",
                kind="office_generate",
                title="Generate Office artifact",
                worker="workmode.office",
                description="Generate the document in the backend.",
                expected_artifacts=[artifact_format],
                metadata={"artifact_format": artifact_format},
            ),
            WorkStep(
                id="office-present",
                kind="artifact_present",
                title=present_title,
                worker="workmode.presenter",
                description=present_description,
                visible_action=visible_action,
                depends_on=["office-generate"],
                metadata={"artifact_kind": artifact_format},
            ),
        ]

    if path == ExecutionPath.BROWSER:
        title = "Open browser evidence" if visible_action else "Record browser task"
        description = (
            "Open a browser source so the operator can verify visible evidence."
            if visible_action
            else "Keep browser work headless and record the task in the audit stream."
        )
        metadata: dict[str, Any] = {}
        if is_web_search_intent(message):
            metadata = {
                "research": True,
                "query": infer_search_query_from_message(message),
                "max_sources": 3,
            }
            title = "Research web sources" if visible_action else "Research web sources headlessly"
            description = (
                "Search the web, open source pages, and save proof for operator verification."
                if visible_action
                else "Search the web, read source pages, and save proof in the audit trail."
            )
        else:
            url = infer_url_from_message(message)
            metadata = {"url": url} if url else {}

        return [
            WorkStep(
                id="browser-source",
                kind="browser_source",
                title=title,
                worker="workmode.browser",
                description=description,
                visible_action=visible_action,
                metadata=metadata,
            )
        ]

    if path == ExecutionPath.WECHAT:
        return [
            WorkStep(
                id="wechat-prepare",
                kind="wechat_prepare",
                title="Prepare WeChat dispatch",
                worker="workmode.wechat",
                description="Prepare a real UI WeChat action with OCR and send confirmation.",
                visible_action=visible_action,
                requires_confirmation=True,
            ),
            WorkStep(
                id="wechat-confirm",
                kind="confirmation_gate",
                title="Require send confirmation",
                worker="workmode.policy",
                description="Pause before any real WeChat send action.",
                requires_confirmation=True,
                depends_on=["wechat-prepare"],
                metadata={"action": "send_message"},
            ),
        ]

    if path == ExecutionPath.DESKTOP:
        app_name = infer_desktop_app_name(message)
        metadata = {"app_name": app_name} if app_name else {}
        title = (
            f"Open {app_name} and capture proof"
            if app_name and visible_action
            else "Capture desktop state"
        )
        description = (
            "Open the requested desktop application and capture visible proof."
            if app_name and visible_action
            else "Capture desktop evidence for the current task."
        )

        return [
            WorkStep(
                id="desktop-capture",
                kind="desktop_capture",
                title=title,
                worker="workmode.desktop",
                description=description,
                visible_action=visible_action,
                metadata=metadata,
                expected_artifacts=["screenshot"],
            )
        ]

    if path == ExecutionPath.BACKEND_WITH_PRESENTATION:
        present_title = "Prepare result presentation" if visible_action else "Record backend result"
        present_description = (
            "Keep the important backend result ready for visible presentation."
            if visible_action
            else "Record the backend result in the audit stream without opening desktop windows."
        )

        return [
            WorkStep(
                id="backend-process",
                kind="backend_process",
                title="Process backend result",
                worker="workmode.backend",
                description="Complete backend processing for the request.",
            ),
            WorkStep(
                id="result-present",
                kind="result_present",
                title=present_title,
                worker="workmode.presenter",
                description=present_description,
                visible_action=visible_action,
                depends_on=["backend-process"],
            ),
        ]

    return [
        WorkStep(
            id="backend-only",
            kind="backend_only",
            title="Complete backend processing",
            worker="workmode.backend",
            description="Complete simple backend processing without opening desktop windows.",
            visible_action=False,
        )
    ]


def _summary_for_path(path: ExecutionPath, *, policy: ModePolicy) -> str:
    if not policy.visible_actions:
        if path == ExecutionPath.OFFICE:
            return "I will generate the Office artifact in the backend and record its path."
        if path in {ExecutionPath.BROWSER, ExecutionPath.DESKTOP}:
            return "I will keep this task headless and record the audit trail."
        if path == ExecutionPath.WECHAT:
            return "I will not send through WeChat UI in headless mode without explicit confirmation."
        if path == ExecutionPath.BACKEND_WITH_PRESENTATION:
            return "I will process the request in the backend and record the result."

    if path == ExecutionPath.OFFICE:
        return "I will generate an Office artifact and expose the result for verification."
    if path == ExecutionPath.BROWSER:
        return "I will use visible browser evidence for the task."
    if path == ExecutionPath.WECHAT:
        return "I will prepare WeChat UI work and require confirmation before sending."
    if path == ExecutionPath.DESKTOP:
        return "I will capture visible desktop evidence."
    if path == ExecutionPath.BACKEND_WITH_PRESENTATION:
        return "I will do backend processing and keep the important result visible."
    return "I will complete the task in the backend."
