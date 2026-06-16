from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from reins.features.workmode.events import WorkEvent
from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkPlan, WorkStep, build_fallback_plan
from reins.features.workmode.policy import get_mode_policy
from reins.features.workmode.router import ExecutionPath, choose_execution_path


StepWorker = Callable[[WorkStep, WorkExecutionState], AsyncIterator[WorkEvent]]


class WorkModeOrchestrator:
    async def run(self, message: str, mode: str = "work") -> AsyncIterator[WorkEvent]:
        task_id = str(uuid4())
        policy = get_mode_policy(mode)
        path = choose_execution_path(message)
        plan = build_fallback_plan(message, policy=policy, path=path)
        state = WorkExecutionState(
            task_id=task_id,
            message=message,
            mode_policy=policy,
            plan_id=plan.id,
        )
        summary: dict[str, Any] = {
            "mode": policy.mode,
            "execution_path": path.value,
            "policy": policy.to_dict(),
            "plan": plan.to_dict(),
            "status": "running",
            "artifacts": [],
            "sources": [],
            "desktop_actions": [],
            "step_results": [],
            "failures": [],
        }

        yield WorkEvent(
            type="task_started",
            task_id=task_id,
            message="任务已开始。",
            data={
                "mode": policy.mode,
                "execution_path": path.value,
                "plan_id": plan.id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        yield WorkEvent(
            type="work.plan.started",
            task_id=task_id,
            message="正在生成工作计划。",
            data={
                "mode": policy.mode,
                "execution_path": path.value,
            },
        )

        yield WorkEvent(
            type="work.plan.fallback",
            task_id=task_id,
            message="已使用本地路由生成 MVP 工作计划。",
            data={
                "planner": plan.planner,
                "reason": "hermes_planner_not_enabled",
            },
        )

        yield WorkEvent(
            type="work.plan.completed",
            task_id=task_id,
            message="工作计划已生成。",
            data={
                "plan": plan.to_dict(),
            },
        )

        route_event = WorkEvent(
            type="step_started",
            task_id=task_id,
            message=f"已选择执行路径：{path.value}",
            data={
                "execution_path": path.value,
                "plan_id": plan.id,
            },
        )
        self._remember_event(summary, route_event)
        yield route_event

        try:
            async for event in self._run_plan(plan, task_id, summary, state):
                yield event

            summary["status"] = "failed" if summary["failures"] else "completed"

            if summary["status"] == "failed":
                yield WorkEvent(
                    type="task_failed",
                    task_id=task_id,
                    message="任务执行中包含失败动作。",
                    data={
                        "execution_path": path.value,
                        "failures": list(summary["failures"]),
                    },
                )

        except Exception as exc:
            summary["status"] = "failed"
            failure = {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "execution_path": path.value,
            }
            summary["failures"].append(failure)

            yield WorkEvent(
                type="task_failed",
                task_id=task_id,
                message=f"任务执行失败：{failure['error']}",
                data=failure,
            )

        yield WorkEvent(
            type="task_finished",
            task_id=task_id,
            message="任务已完成。" if summary["status"] == "completed" else "任务已结束，但有失败。",
            data=self._finalize_summary(summary),
        )

    async def _run_plan(
        self,
        plan: WorkPlan,
        task_id: str,
        summary: dict[str, Any],
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        for step in plan.steps:
            missing = [
                dependency
                for dependency in step.depends_on
                if state.step_status.get(dependency) != "completed"
            ]

            if missing:
                failure = {
                    "error_type": "StepDependencyError",
                    "error": f"Step {step.id} is waiting on incomplete dependencies: {', '.join(missing)}",
                    "step_id": step.id,
                    "missing_dependencies": missing,
                }
                summary["failures"].append(failure)
                state.step_status[step.id] = "blocked"
                step_result = {
                    "step_id": step.id,
                    "status": "blocked",
                    "missing_dependencies": missing,
                }
                summary["step_results"].append(step_result)

                yield WorkEvent(
                    type="work.step.failed",
                    task_id=task_id,
                    message=f"步骤无法执行：{step.title}",
                    data={
                        "step": step.to_dict(),
                        "result": step_result,
                    },
                )
                break

            try:
                worker = self._worker_for_step(step.kind)
            except ValueError as exc:
                failure = {
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "step_id": step.id,
                }
                summary["failures"].append(failure)
                state.step_status[step.id] = "failed"
                step_result = {
                    "step_id": step.id,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                summary["step_results"].append(step_result)

                yield WorkEvent(
                    type="work.step.failed",
                    task_id=task_id,
                    message=f"步骤失败：{step.title}",
                    data={
                        "step": step.to_dict(),
                        "result": step_result,
                    },
                )
                break

            async for event in self._run_plan_step(step, worker, task_id, summary, state):
                yield event

            if state.step_status.get(step.id) != "completed":
                break

    def _worker_for_step(self, kind: str) -> StepWorker:
        workers: dict[str, StepWorker] = {
            "backend_only": self._worker_backend_only,
            "backend_process": self._worker_backend_process,
            "result_present": self._worker_result_present,
            "office_generate": self._worker_office_generate,
            "artifact_present": self._worker_artifact_present,
            "browser_source": self._worker_browser_source,
            "desktop_capture": self._worker_desktop_capture,
            "wechat_prepare": self._worker_wechat_prepare,
            "confirmation_gate": self._worker_confirmation_gate,
        }

        try:
            return workers[kind]
        except KeyError as exc:
            known = ", ".join(sorted(workers))
            raise ValueError(f"Unknown work step kind: {kind}. Expected one of: {known}") from exc

    async def _run_plan_step(
        self,
        step: WorkStep,
        worker: StepWorker,
        task_id: str,
        summary: dict[str, Any],
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        failure_count = len(summary["failures"])

        yield WorkEvent(
            type="work.step.started",
            task_id=task_id,
            message=f"开始步骤：{step.title}",
            data={
                "step": step.to_dict(),
            },
        )

        try:
            async for event in worker(step, state):
                self._remember_event(summary, event, state)
                yield event
        except Exception as exc:
            state.step_status[step.id] = "failed"
            step_result = {
                "step_id": step.id,
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            summary["step_results"].append(step_result)

            yield WorkEvent(
                type="work.step.failed",
                task_id=task_id,
                message=f"步骤失败：{step.title}",
                data={
                    "step": step.to_dict(),
                    "result": step_result,
                },
            )
            raise

        new_failures = list(summary["failures"][failure_count:])

        if new_failures:
            state.step_status[step.id] = "failed"
            step_result = {
                "step_id": step.id,
                "status": "failed",
                "failures": new_failures,
            }
            summary["step_results"].append(step_result)

            yield WorkEvent(
                type="work.step.failed",
                task_id=task_id,
                message=f"步骤失败：{step.title}",
                data={
                    "step": step.to_dict(),
                    "result": step_result,
                },
            )
            return

        state.step_status[step.id] = "completed"
        step_result = {
            "step_id": step.id,
            "status": "completed",
        }
        summary["step_results"].append(step_result)

        yield WorkEvent(
            type="work.step.completed",
            task_id=task_id,
            message=f"步骤完成：{step.title}",
            data={
                "step": step.to_dict(),
                "result": step_result,
            },
        )

    async def _worker_backend_only(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        async for event in self._run_backend_only(state.task_id, state.message):
            yield event

    async def _worker_backend_process(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        yield WorkEvent(
            type="step_started",
            task_id=state.task_id,
            message="正在后台处理内容。",
            data={
                "input": state.message,
                "step_id": step.id,
            },
        )

        state.scratch["backend_result"] = {
            "summary": state.message,
        }

        yield WorkEvent(
            type="step_finished",
            task_id=state.task_id,
            message="后台处理完成。",
            data={
                "input": state.message,
                "step_id": step.id,
            },
        )

    async def _worker_result_present(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        policy = state.mode_policy

        yield WorkEvent(
            type="step_finished",
            task_id=state.task_id,
            message="已准备结果展示。" if policy.visible_actions else "已按当前模式记录后台结果。",
            data={
                "input": state.message,
                "mode": policy.mode,
                "visible_actions": policy.visible_actions,
                "backend_result": state.scratch.get("backend_result", {}),
            },
        )

    async def _worker_office_generate(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        from reins.features.workmode.artifacts import generate_demo_docx

        yield WorkEvent(
            type="step_started",
            task_id=state.task_id,
            message="正在后台生成 Office 文档。",
            data={
                "step_id": step.id,
            },
        )

        path = generate_demo_docx(
            title="Community Operations Report",
            body=f"Task request: {state.message}",
        )

        yield WorkEvent(
            type="artifact_created",
            task_id=state.task_id,
            message="Word 文档已生成。",
            data={
                "path": str(path),
                "kind": "docx",
                "step_id": step.id,
            },
        )

    async def _worker_artifact_present(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        policy = state.mode_policy
        artifact_kind = str(step.metadata.get("artifact_kind", "docx"))
        artifact = state.latest_artifact(artifact_kind)

        if artifact is None:
            raise RuntimeError(f"No {artifact_kind} artifact is available for presentation.")

        if not policy.visible_actions or not policy.show_office_windows:
            yield WorkEvent(
                type="step_finished",
                task_id=state.task_id,
                message="已按当前模式跳过 Office 可见展示。",
                data={
                    "input": state.message,
                    "mode": policy.mode,
                    "visible_actions": policy.visible_actions,
                    "show_office_windows": policy.show_office_windows,
                    "artifact": artifact,
                },
            )
            return

        from reins.features.computer.desktop import get_desktop_backend

        desktop = get_desktop_backend()
        open_result = desktop.open_file(str(artifact["path"]))

        yield WorkEvent(
            type="desktop_action",
            task_id=state.task_id,
            message="已打开文档供核验。",
            data=open_result,
        )

        screenshot_result = desktop.screenshot()

        yield WorkEvent(
            type="desktop_action",
            task_id=state.task_id,
            message="已保存桌面截图作为执行证据。",
            data=screenshot_result,
        )

    async def _worker_browser_source(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        policy = state.mode_policy

        if not policy.visible_actions:
            yield WorkEvent(
                type="step_finished",
                task_id=state.task_id,
                message="已按当前模式跳过浏览器可见操作。",
                data={
                    "input": state.message,
                    "mode": policy.mode,
                    "visible_actions": policy.visible_actions,
                },
            )
            return

        from reins.features.computer.desktop import get_desktop_backend

        desktop = get_desktop_backend()

        yield WorkEvent(
            type="browser_action",
            task_id=state.task_id,
            message="正在打开浏览器进行可见操作。",
            data={
                "input": state.message,
            },
        )

        result = desktop.open_url("https://example.com")

        yield WorkEvent(
            type="browser_action",
            task_id=state.task_id,
            message="浏览器已打开。",
            data=result,
        )

        if result.get("ok"):
            yield WorkEvent(
                type="source_opened",
                task_id=state.task_id,
                message="已记录可核验来源。",
                data={
                    "title": "Example Domain",
                    "url": "https://example.com",
                    "step_id": step.id,
                },
            )

    async def _worker_desktop_capture(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        policy = state.mode_policy

        if not policy.visible_actions:
            yield WorkEvent(
                type="step_finished",
                task_id=state.task_id,
                message="已按当前模式跳过桌面可见操作。",
                data={
                    "input": state.message,
                    "mode": policy.mode,
                    "visible_actions": policy.visible_actions,
                },
            )
            return

        from reins.features.computer.desktop import get_desktop_backend

        desktop = get_desktop_backend()

        yield WorkEvent(
            type="desktop_action",
            task_id=state.task_id,
            message="正在保存桌面截图。",
            data={
                "input": state.message,
            },
        )

        result = desktop.screenshot()

        yield WorkEvent(
            type="desktop_action",
            task_id=state.task_id,
            message="桌面截图已保存。",
            data=result,
        )

    async def _worker_wechat_prepare(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        yield WorkEvent(
            type="confirmation_required",
            task_id=state.task_id,
            message="微信真实 UI 操作尚未在 MVP 中启用。后续需要 OCR、窗口确认和发送前确认。",
            data={
                "input": state.message,
                "step_id": step.id,
            },
        )

    async def _worker_confirmation_gate(
        self,
        step: WorkStep,
        state: WorkExecutionState,
    ) -> AsyncIterator[WorkEvent]:
        yield WorkEvent(
            type="confirmation_required",
            task_id=state.task_id,
            message="需要确认后才会继续执行敏感动作。",
            data={
                "action": step.metadata.get("action"),
                "step_id": step.id,
                "requires_confirmation": True,
            },
        )

    def _remember_event(
        self,
        summary: dict[str, Any],
        event: WorkEvent,
        state: WorkExecutionState | None = None,
    ) -> None:
        if event.type == "artifact_created":
            artifact = dict(event.data)
            summary["artifacts"].append(artifact)

            if state is not None:
                state.add_artifact(artifact)

            return

        if event.type == "source_opened":
            source = dict(event.data)
            summary["sources"].append(source)

            if state is not None:
                state.add_source(source)

            return

        if event.type in {"desktop_action", "browser_action"}:
            action = dict(event.data)
            if action:
                summary["desktop_actions"].append(action)

            if action.get("ok") is False:
                summary["failures"].append(
                    {
                        "error_type": "ActionFailed",
                        "error": action.get("error", "Desktop action failed"),
                        "event_type": event.type,
                    }
                )

    def _finalize_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        finalized = dict(summary)
        finalized["artifact_count"] = len(finalized["artifacts"])
        finalized["source_count"] = len(finalized["sources"])
        finalized["desktop_action_count"] = len(finalized["desktop_actions"])
        finalized["step_count"] = len(finalized["step_results"])
        finalized["failure_count"] = len(finalized["failures"])
        finalized["artifact_paths"] = [
            artifact["path"]
            for artifact in finalized["artifacts"]
            if isinstance(artifact.get("path"), str)
        ]
        finalized["source_urls"] = [
            source["url"]
            for source in finalized["sources"]
            if isinstance(source.get("url"), str)
        ]
        finalized["finished_at"] = datetime.now(timezone.utc).isoformat()
        return finalized

    async def _run_backend_only(self, task_id: str, message: str):
        yield WorkEvent(
            type="step_finished",
            task_id=task_id,
            message="已完成后台处理。",
            data={
                "input": message,
            },
        )
