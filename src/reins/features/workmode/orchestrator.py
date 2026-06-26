from __future__ import annotations

from collections.abc import AsyncIterator
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
            "desktop_actions": [],
            "ocr": [],
            "sources": [],
            "pending_confirmations": [],
            "failures": [],
            "observations": [],
            "started_at": created_at,
        }

        # HELPERS
        def emit(event_type: str, message: str, data: dict | None = None):
            event = WorkEvent(
                type=event_type,
                task_id=task_id,
                message=message,
                data=data or {},
            )
            try:
                save_event(issue.case_id, event.type, event.message, event.data)
            except Exception:
                pass
            return event

        def persist_case(status: str):
            try:
                save_case({
                    "case_id": issue.case_id,
                    "message": message,
                    "issue_type": issue.issue_type,
                    "priority": issue.priority,
                    "location": issue.location,
                    "workflow": workflow,
                    "status": status,
                    "created_at": created_at,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass

        def has_artifact(artifact: dict[str, Any]) -> bool:
            artifact_path = artifact.get("path")
            for existing in summary["artifacts"]:
                if isinstance(existing, dict) and artifact_path and existing.get("path") == artifact_path:
                    return True
            return False

        # START
        persist_case("running")

        yield emit("task_started", "WorkMode started", {
            "mode": policy.mode,
            "execution_path": path.value,
            "plan_id": plan.id,
            "planner": plan.planner,
            "hermes_error": hermes_error,
            "intake": intake,
            "started_at": created_at,
        })

        if hermes_error:
            yield emit("work.plan.fallback", "Hermes planner failed. Using fallback planner.", {
                "planner": "fallback_router",
                "hermes_error": hermes_error,
            })

        yield emit("work.plan.started", "Planning started", {
            "planner": plan.planner,
            "execution_path": path.value,
        })
        yield emit("work.plan.completed", "Plan created", {"plan": plan_data})

        # EXECUTION LOOP (STRICT MODE)
        for step in plan.steps:

            yield emit("work.step.started", "Step started", {
                "step_id": step.id,
                "kind": step.kind,
                "step": step.to_dict(),
            })

            result = None

            try:
                # STRICT VALIDATION
                ExecutionContract.validate(step.kind)

                domain = WorkerRouter.route_kind(step.kind)

                # EXECUTION
                result = await run_worker(step, state)

            except Exception as exc:
                summary["failures"].append({
                    "step_id": step.id,
                    "error": str(exc),
                })

                yield emit("work.step.failed", "Step failed", {
                    "step": step.to_dict(),
                    "step_id": step.id,
                    "step_kind": step.kind,
                    "error": str(exc),
                })
                summary["status"] = "failed"
                break

            if isinstance(result, dict) and result.get("ok") is False:
                failure = {
                    "step_id": step.id,
                    "step_kind": step.kind,
                    "error": result.get("error") or result.get("message") or "Worker returned an unsuccessful result.",
                    "error_type": result.get("error_type") or "WorkerError",
                    "result": result,
                }
                summary["failures"].append(failure)
                summary["status"] = "failed"
                yield emit("work.step.failed", str(failure["error"]), {
                    "step": step.to_dict(),
                    **failure,
                })
                break

            # OBSERVATION
            observation = {
                "step_id": step.id,
                "kind": step.kind,
                "result": result,
            }

            summary["observations"].append(observation)

            # ARTIFACTS
            if isinstance(result, dict):

                if result.get("artifact"):
                    artifact = result["artifact"]
                    if not has_artifact(artifact):
                        summary["artifacts"].append(artifact)
                        try:
                            save_artifact(issue.case_id, artifact)
                        except Exception:
                            pass
                        yield emit("artifact_created", str(artifact.get("summary") or artifact.get("title") or "Artifact created"), {
                            **artifact,
                            "step_id": step.id,
                        })

                if result.get("screenshots"):
                    summary["screenshots"].extend(result["screenshots"])

                if result.get("browser"):
                    summary["browser_pages"].append(result["browser"])

                if result.get("sources"):
                    for source in result["sources"]:
                        summary["sources"].append(source)
                        yield emit("source_opened", str(source.get("title") or source.get("url") or "Source opened"), {
                            **source,
                            "step_id": step.id,
                        })

                if result.get("browser_actions"):
                    for action in result["browser_actions"]:
                        yield emit("browser_action", str(action.get("title") or action.get("kind") or "Browser action"), {
                            **action,
                            "step_id": step.id,
                        })

                if result.get("desktop_actions"):
                    for action in result["desktop_actions"]:
                        summary["desktop_actions"].append(action)
                        yield emit("desktop_action", str(action.get("title") or action.get("kind") or "Desktop action"), {
                            **action,
                            "step_id": step.id,
                        })

                if result.get("desktop"):
                    summary["desktop_actions"].append(result["desktop"])

                if result.get("ocr"):
                    summary["ocr"].append(result["ocr"])

                if result.get("confirmation"):
                    confirmation = result["confirmation"]
                    summary["pending_confirmations"].append(confirmation)
                    summary["status"] = "pending_confirmation"
                    yield emit("confirmation_required", str(result.get("message") or "Confirmation required before continuing."), {
                        "step": step.to_dict(),
                        "step_id": step.id,
                        "step_kind": step.kind,
                        "confirmation": confirmation,
                        "result": result,
                    })
                    yield emit("work.step.blocked", "Step is waiting for operator confirmation.", {
                        "step": step.to_dict(),
                        "step_id": step.id,
                        "step_kind": step.kind,
                        "result": {
                            **result,
                            "status": "blocked",
                            "reason": "pending_confirmation",
                        },
                    })
                    break

            yield emit("work.step.completed", "Step completed", {
                "step": step.to_dict(),
                "step_id": step.id,
                "step_kind": step.kind,
                "result": result,
                "domain": domain,
            })

        # FINALIZE
        if summary["status"] == "running":
            summary["status"] = "completed"
        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        summary["artifact_count"] = len(summary["artifacts"])
        summary["source_count"] = len(summary["sources"])
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

        yield emit("task_finished", finish_message, {
            **summary,
            "summary": summary,
            "intake": intake,
        })
