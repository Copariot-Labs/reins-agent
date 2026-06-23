from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from uuid import uuid4

from reins.features.workmode.events import WorkEvent
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep, build_fallback_plan
from reins.features.workmode.policy import get_mode_policy
from reins.features.workmode.router import choose_execution_path

# INTAKE LAYER
from reins.features.workmode.intake.parser import ResidentIntakeParser
from reins.features.workmode.intake.router import route_issue

# DB LAYER
from reins.features.workmode.db import save_artifact, save_case, save_event

# HERMES PLANNER
from reins.features.workmode.hermes_planner import try_build_hermes_plan

# WORKER ROUTING
from reins.features.workmode.workers import run_worker


StepWorker = Callable[[WorkStep, WorkExecutionState], AsyncIterator[WorkEvent]]


class WorkModeOrchestrator:
    # MAIN ENTRY
    async def run(self, message: str, mode: str = "work") -> AsyncIterator[WorkEvent]:
        task_id = str(uuid4())
        policy = get_mode_policy(mode)

        # P2: INTAKE
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

        # P5: HERMES PLANNER WITH SAFE FALLBACK
        plan, hermes_error = try_build_hermes_plan(
            issue.description,
            policy=policy,
            path=path,
            intake=intake,
        )

        if plan is None:
            plan = build_fallback_plan(
                issue.description,
                policy=policy,
                path=path,
            )

        # STATE
        state = WorkExecutionState(
            task_id=task_id,
            message=message,
            mode_policy=policy,
            plan_id=plan.id,
        )

        state.scratch["intake"] = intake

        created_at = datetime.now(timezone.utc).isoformat()

        # SAVE CASE CREATE
        save_case(
            {
                "case_id": issue.case_id,
                "message": message,
                "issue_type": issue.issue_type,
                "priority": issue.priority,
                "location": issue.location,
                "workflow": workflow,
                "status": "running",
                "created_at": created_at,
                "updated_at": created_at,
            }
        )

        # EVENT PERSISTENCE HELPER
        def persist(event: WorkEvent) -> None:
            """
            Persist event to SQLite.

            Important:
            DB persistence should never break the live WorkMode stream.
            """
            try:
                save_event(
                    case_id=issue.case_id,
                    event_type=event.type,
                    message=event.message,
                    data=event.data or {},
                )
            except Exception:
                pass

        # TASK STARTED
        event = WorkEvent(
            type="task_started",
            task_id=task_id,
            message="WorkMode started",
            data={
                "mode": policy.mode,
                "execution_path": path.value,
                "plan_id": plan.id,
                "planner": plan.planner,
                "hermes_error": hermes_error,
                "intake": intake,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        persist(event)
        yield event

        # HERMES FALLBACK EVENT
        if hermes_error:
            event = WorkEvent(
                type="work.plan.fallback",
                task_id=task_id,
                message="Hermes planner failed. Using fallback planner.",
                data={
                    "planner": "fallback_router",
                    "hermes_error": hermes_error,
                },
            )
            persist(event)
            yield event

        # PLAN STARTED
        event = WorkEvent(
            type="work.plan.started",
            task_id=task_id,
            message="Planning started",
            data={
                "planner": plan.planner,
            },
        )
        persist(event)
        yield event

        # PLAN COMPLETED
        event = WorkEvent(
            type="work.plan.completed",
            task_id=task_id,
            message="Plan created",
            data={
                "plan": plan.to_dict(),
            },
        )
        persist(event)
        yield event

        # SUMMARY
        summary = {
            "task_id": task_id,
            "status": "running",
            "planner": plan.planner,
            "artifacts": [],
            "sources": [],
            "failures": [],
        }

        # EXECUTION LOOP
        for step in plan.steps:
            # STEP STARTED
            event = WorkEvent(
                type="work.step.started",
                task_id=task_id,
                message=f"Running step: {step.title}",
                data={
                    "step_id": step.id,
                    "step_kind": step.kind,
                    "worker": step.worker,
                },
            )
            persist(event)
            yield event

            # EXECUTE STEP WITH FAILURE HANDLING
            try:
                result = await self._run_step(step, state)

            except Exception as exc:
                summary["status"] = "failed"

                failure = {
                    "step_id": step.id,
                    "step_title": step.title,
                    "step_kind": step.kind,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

                summary["failures"].append(failure)

                event = WorkEvent(
                    type="task_failed",
                    task_id=task_id,
                    message=f"Task failed during step: {step.title}",
                    data={
                        "summary": summary,
                        "failure": failure,
                        "intake": intake,
                    },
                )
                persist(event)
                yield event

                break

            # STEP COMPLETED
            event = WorkEvent(
                type="work.step.completed",
                task_id=task_id,
                message=f"Finished step: {step.title}",
                data={
                    "step_id": step.id,
                    "step_kind": step.kind,
                    "result": result,
                },
            )
            persist(event)
            yield event

            # ARTIFACT TRACKING
            if isinstance(result, dict) and result.get("artifact"):
                artifact = result["artifact"]
                summary["artifacts"].append(artifact)

                try:
                    save_artifact(
                        case_id=issue.case_id,
                        artifact=artifact,
                    )
                except Exception as exc:
                    failure = {
                        "step_id": step.id,
                        "step_title": step.title,
                        "step_kind": step.kind,
                        "error_type": "ArtifactSaveError",
                        "error": str(exc),
                    }
                    summary["failures"].append(failure)

            # SOURCE TRACKING
            if isinstance(result, dict) and result.get("sources"):
                sources = result["sources"]

                if isinstance(sources, list):
                    summary["sources"].extend(sources)

        # FINAL STATUS
        final_status = "completed" if not summary["failures"] else "failed"
        summary["status"] = final_status

        # SAVE CASE FINAL UPDATE
        save_case(
            {
                "case_id": issue.case_id,
                "message": message,
                "issue_type": issue.issue_type,
                "priority": issue.priority,
                "location": issue.location,
                "workflow": workflow,
                "status": final_status,
                "created_at": created_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        # TASK FINISHED
        event = WorkEvent(
            type="task_finished",
            task_id=task_id,
            message="Task completed"
            if final_status == "completed"
            else "Task finished with failure",
            data={
                "summary": summary,
                "intake": intake,
            },
        )
        persist(event)
        yield event

    # STEP EXECUTOR
    async def _run_step(self, step: WorkStep, state: WorkExecutionState):
        return await run_worker(step, state)