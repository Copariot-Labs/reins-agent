from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

# CORE
from reins.features.workmode.events import WorkEvent
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import build_fallback_plan
from reins.features.workmode.policy import get_mode_policy
from reins.features.workmode.router import choose_execution_path

from reins.features.workmode.intake.parser import ResidentIntakeParser
from reins.features.workmode.intake.router import route_issue

from reins.features.workmode.hermes_planner import try_build_hermes_plan
from reins.features.workmode.workers import run_worker

from reins.features.workmode.db import save_artifact, save_case, save_event

# STABILITY
from reins.features.workmode.runtime.worker_router import WorkerRouter
from reins.features.workmode.runtime.execution_contract import ExecutionContract


class WorkModeOrchestrator:
    async def run(self, message: str, mode: str = "work") -> AsyncIterator[WorkEvent]:
        # INIT
        task_id = str(uuid4())
        policy = get_mode_policy(mode)

        parser = ResidentIntakeParser()
        issue = parser.parse(message)

        workflow = route_issue(issue)
        path = choose_execution_path(issue.description)

        intake = {
            "case_id": issue.case_id,
            "issue_type": issue.issue_type,
            "priority": issue.priority,
            "location": issue.location,
            "workflow": workflow,
        }

        created_at = datetime.now(timezone.utc).isoformat()

        # PLAN
        plan, hermes_error = try_build_hermes_plan(
            issue.description,
            policy=policy,
            path=path,
            intake=intake,
        )

        if plan is None:
            plan = build_fallback_plan(issue.description, policy=policy, path=path)

        plan_data = plan.to_dict()

        # STATE
        state = WorkExecutionState(
            task_id=task_id,
            message=message,
            mode_policy=policy,
            plan_id=plan.id,
        )

        state.scratch["intake"] = intake
        state.scratch.setdefault("previous_outputs", [])

        # SUMMARY
        summary: dict[str, Any] = {
            "task_id": task_id,
            "status": "running",
            "mode": policy.mode,
            "execution_path": path.value,
            "policy": policy.to_dict(),
            "plan": plan_data,
            "artifacts": [],
            "screenshots": [],
            "browser_pages": [],
            "research": [],
            "desktop_actions": [],
            "ocr": [],
            "sources": [],
            "pending_confirmations": [],
            "failures": [],
            "observations": [],
            "started_at": created_at,
        }

        # HELPERS
        def emit(event_type: str, event_message: str, data: dict | None = None) -> WorkEvent:
            event = WorkEvent(
                type=event_type,
                task_id=task_id,
                message=event_message,
                data=data or {},
            )

            try:
                save_event(issue.case_id, event.type, event.message, event.data)
            except Exception:
                pass

            return event

        def persist_case(status: str) -> None:
            try:
                save_case(
                    {
                        "case_id": issue.case_id,
                        "message": message,
                        "issue_type": issue.issue_type,
                        "priority": issue.priority,
                        "location": issue.location,
                        "workflow": workflow,
                        "status": status,
                        "created_at": created_at,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception:
                pass

        def has_artifact(artifact: dict[str, Any]) -> bool:
            artifact_path = artifact.get("path")
            artifact_title = artifact.get("title")
            artifact_kind = artifact.get("kind") or artifact.get("type")

            for existing in summary["artifacts"]:
                if not isinstance(existing, dict):
                    continue

                if artifact_path and existing.get("path") == artifact_path:
                    return True

                if (
                    not artifact_path
                    and artifact_title
                    and artifact_kind
                    and existing.get("title") == artifact_title
                    and (existing.get("kind") or existing.get("type")) == artifact_kind
                ):
                    return True

            return False

        def has_source(source: dict[str, Any]) -> bool:
            source_url = source.get("url")
            source_title = source.get("title")

            for existing in summary["sources"]:
                if not isinstance(existing, dict):
                    continue

                if source_url and existing.get("url") == source_url:
                    return True

                if not source_url and source_title and existing.get("title") == source_title:
                    return True

            return False

        def remember_previous_output(step_id: str, result: dict[str, Any]) -> None:
            previous_outputs = state.scratch.setdefault("previous_outputs", [])

            if not isinstance(previous_outputs, list):
                previous_outputs = []
                state.scratch["previous_outputs"] = previous_outputs

            output = result.get("output") or result.get("message") or result.get("summary")

            if output:
                previous_outputs.append(
                    {
                        "step_id": step_id,
                        "output": output,
                    }
                )

        def merge_context(result: dict[str, Any]) -> None:
            context = result.get("context")

            if isinstance(context, dict):
                state.scratch.update(context)

        def progress_event_from_payload(payload: dict[str, Any], step) -> WorkEvent:
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

            enriched = {
                "step": step.to_dict(),
                "step_id": step.id,
                "step_kind": step.kind,
                **data,
            }

            return emit(
                str(payload.get("type") or "work.step.progress"),
                str(payload.get("message") or "Step progress"),
                enriched,
            )

        async def run_worker_with_progress(step):
            progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            state.progress_queue = progress_queue
            state.current_step_id = step.id
            state.current_step_kind = step.kind

            worker_task = asyncio.create_task(run_worker(step, state))

            try:
                while not worker_task.done():
                    progress_task = asyncio.create_task(progress_queue.get())

                    done, pending = await asyncio.wait(
                        {worker_task, progress_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if progress_task in done:
                        yield progress_event_from_payload(progress_task.result(), step), None
                    else:
                        progress_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await progress_task

                    for task in pending:
                        if task is not worker_task:
                            task.cancel()
                            with suppress(asyncio.CancelledError):
                                await task

                result = worker_task.result()

                while not progress_queue.empty():
                    yield progress_event_from_payload(progress_queue.get_nowait(), step), None

                yield None, result

            finally:
                state.progress_queue = None
                state.current_step_id = None
                state.current_step_kind = None

        # START
        persist_case("running")

        yield emit(
            "task_started",
            "WorkMode started",
            {
                "mode": policy.mode,
                "execution_path": path.value,
                "plan_id": plan.id,
                "planner": plan.planner,
                "hermes_error": hermes_error,
                "intake": intake,
                "started_at": created_at,
            },
        )

        if hermes_error:
            yield emit(
                "work.plan.fallback",
                "Hermes planner failed. Using fallback planner.",
                {
                    "planner": "fallback_router",
                    "hermes_error": hermes_error,
                },
            )

        yield emit(
            "work.plan.started",
            "Planning started",
            {
                "planner": plan.planner,
                "execution_path": path.value,
            },
        )

        yield emit(
            "work.plan.completed",
            "Plan created",
            {
                "plan": plan_data,
            },
        )

        # EXECUTION LOOP
        for step in plan.steps:
            yield emit(
                "work.step.started",
                "Step started",
                {
                    "step_id": step.id,
                    "kind": step.kind,
                    "step": step.to_dict(),
                },
            )

            result: Any = None
            domain: str | None = None

            try:
                # STRICT VALIDATION
                ExecutionContract.validate(step.kind)

                domain = WorkerRouter.route_kind(step.kind)

                # EXECUTION
                async for progress_event, worker_result in run_worker_with_progress(step):
                    if progress_event is not None:
                        yield progress_event
                    else:
                        result = worker_result

            except Exception as exc:
                failure = {
                    "step_id": step.id,
                    "step_kind": step.kind,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }

                summary["failures"].append(failure)
                summary["status"] = "failed"

                yield emit(
                    "work.step.failed",
                    "Step failed",
                    {
                        "step": step.to_dict(),
                        **failure,
                    },
                )
                break

            if isinstance(result, dict) and result.get("ok") is False:
                failure = {
                    "step_id": step.id,
                    "step_kind": step.kind,
                    "error": result.get("error")
                    or result.get("message")
                    or "Worker returned an unsuccessful result.",
                    "error_type": result.get("error_type") or "WorkerError",
                    "result": result,
                }

                summary["failures"].append(failure)
                summary["status"] = "failed"

                yield emit(
                    "work.step.failed",
                    str(failure["error"]),
                    {
                        "step": step.to_dict(),
                        **failure,
                    },
                )
                break

            # OBSERVATION
            observation = {
                "step_id": step.id,
                "kind": step.kind,
                "result": result,
            }

            summary["observations"].append(observation)

            # RESULT HARVESTING
            if isinstance(result, dict):
                # Context is important for chained workflows:
                # browser/research/backend -> office_generate
                merge_context(result)
                remember_previous_output(step.id, result)

                # ARTIFACTS
                artifact = result.get("artifact")

                if isinstance(artifact, dict):
                    # Critical: artifact_present depends on state.latest_artifact()
                    state.add_artifact(artifact)

                    if not has_artifact(artifact):
                        summary["artifacts"].append(artifact)

                        try:
                            save_artifact(issue.case_id, artifact)
                        except Exception:
                            pass

                        yield emit(
                            "artifact_created",
                            str(artifact.get("summary") or artifact.get("title") or "Artifact created"),
                            {
                                **artifact,
                                "step_id": step.id,
                            },
                        )

                # SCREENSHOTS
                screenshots = result.get("screenshots")

                if isinstance(screenshots, list):
                    summary["screenshots"].extend(screenshots)

                # BROWSER PAGE
                browser_page = result.get("browser")

                if isinstance(browser_page, dict):
                    summary["browser_pages"].append(browser_page)

                # RESEARCH
                research = result.get("research")

                if isinstance(research, dict):
                    summary["research"].append(research)

                # SOURCES
                sources = result.get("sources")

                if isinstance(sources, list):
                    for source in sources:
                        if not isinstance(source, dict):
                            continue

                        # Critical: Office worker uses state.sources
                        state.add_source(source)

                        if not has_source(source):
                            summary["sources"].append(source)

                            yield emit(
                                "source_opened",
                                str(source.get("title") or source.get("url") or "Source opened"),
                                {
                                    **source,
                                    "step_id": step.id,
                                },
                            )

                # BROWSER ACTIONS
                browser_actions = result.get("browser_actions")

                if isinstance(browser_actions, list):
                    for action in browser_actions:
                        if not isinstance(action, dict):
                            continue

                        yield emit(
                            "browser_action",
                            str(action.get("title") or action.get("kind") or "Browser action"),
                            {
                                **action,
                                "step_id": step.id,
                            },
                        )

                # DESKTOP ACTIONS
                desktop_actions = result.get("desktop_actions")

                if isinstance(desktop_actions, list):
                    for action in desktop_actions:
                        if not isinstance(action, dict):
                            continue

                        summary["desktop_actions"].append(action)

                        yield emit(
                            "desktop_action",
                            str(action.get("title") or action.get("kind") or "Desktop action"),
                            {
                                **action,
                                "step_id": step.id,
                            },
                        )

                desktop = result.get("desktop")

                if isinstance(desktop, dict):
                    summary["desktop_actions"].append(desktop)

                    yield emit(
                        "desktop_action",
                        str(desktop.get("title") or desktop.get("kind") or "Desktop action"),
                        {
                            **desktop,
                            "step_id": step.id,
                        },
                    )

                # OCR
                ocr = result.get("ocr")

                if isinstance(ocr, dict):
                    summary["ocr"].append(ocr)

                # CONFIRMATION
                confirmation = result.get("confirmation")

                if isinstance(confirmation, dict):
                    summary["pending_confirmations"].append(confirmation)
                    summary["status"] = "pending_confirmation"

                    yield emit(
                        "confirmation_required",
                        str(result.get("message") or "Confirmation required before continuing."),
                        {
                            "step": step.to_dict(),
                            "step_id": step.id,
                            "step_kind": step.kind,
                            "confirmation": confirmation,
                            "result": result,
                        },
                    )

                    yield emit(
                        "work.step.blocked",
                        "Step is waiting for operator confirmation.",
                        {
                            "step": step.to_dict(),
                            "step_id": step.id,
                            "step_kind": step.kind,
                            "result": {
                                **result,
                                "status": "blocked",
                                "reason": "pending_confirmation",
                            },
                        },
                    )

                    break

            yield emit(
                "work.step.completed",
                "Step completed",
                {
                    "step": step.to_dict(),
                    "step_id": step.id,
                    "step_kind": step.kind,
                    "result": result,
                    "domain": domain,
                },
            )

        # FINALIZE
        if summary["status"] == "running":
            summary["status"] = "completed"

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()

        summary["artifact_count"] = len(summary["artifacts"])
        summary["source_count"] = len(summary["sources"])
        summary["research_count"] = len(summary["research"])
        summary["desktop_action_count"] = len(summary["desktop_actions"])
        summary["failure_count"] = len(summary["failures"])
        summary["pending_confirmation_count"] = len(summary["pending_confirmations"])

        summary["artifact_paths"] = [
            artifact.get("path")
            for artifact in summary["artifacts"]
            if isinstance(artifact, dict) and artifact.get("path")
        ]

        summary["source_urls"] = [
            source.get("url")
            for source in summary["sources"]
            if isinstance(source, dict) and source.get("url")
        ]

        persist_case(str(summary["status"]))

        finish_message = "Task completed"

        if summary["status"] == "pending_confirmation":
            finish_message = "Task waiting for operator confirmation"
        elif summary["status"] == "failed":
            finish_message = "Task failed"

        yield emit(
            "task_finished",
            finish_message,
            {
                **summary,
                "summary": summary,
                "intake": intake,
            },
        )