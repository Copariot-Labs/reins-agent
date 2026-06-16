from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

from reins.features.workmode.events import WorkEvent
from reins.features.workmode.router import ExecutionPath, choose_execution_path


class WorkModeOrchestrator:
    async def run(self, message: str, mode: str = "work") -> AsyncIterator[WorkEvent]:
        task_id = str(uuid4())
        path = choose_execution_path(message)

        yield WorkEvent(
            type="task_started",
            task_id=task_id,
            message="任务已开始。",
            data={
                "mode": mode,
                "execution_path": path.value,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        yield WorkEvent(
            type="step_started",
            task_id=task_id,
            message=f"已选择执行路径：{path.value}",
            data={
                "execution_path": path.value,
            },
        )

        if path == ExecutionPath.OFFICE:
            async for event in self._run_office(task_id, message):
                yield event

        elif path == ExecutionPath.BROWSER:
            async for event in self._run_browser(task_id, message):
                yield event

        elif path == ExecutionPath.WECHAT:
            async for event in self._run_wechat(task_id, message):
                yield event

        elif path == ExecutionPath.DESKTOP:
            async for event in self._run_desktop(task_id, message):
                yield event

        elif path == ExecutionPath.BACKEND_WITH_PRESENTATION:
            async for event in self._run_backend_with_presentation(task_id, message):
                yield event

        else:
            async for event in self._run_backend_only(task_id, message):
                yield event

        yield WorkEvent(
            type="task_finished",
            task_id=task_id,
            message="任务已完成。",
        )

    async def _run_backend_only(self, task_id: str, message: str):
        yield WorkEvent(
            type="step_finished",
            task_id=task_id,
            message="已完成后台处理。",
            data={
                "input": message,
            },
        )

    async def _run_backend_with_presentation(self, task_id: str, message: str):
        yield WorkEvent(
            type="step_started",
            task_id=task_id,
            message="正在后台处理内容，然后会展示关键结果。",
        )

        yield WorkEvent(
            type="step_finished",
            task_id=task_id,
            message="后台处理完成。",
            data={
                "input": message,
            },
        )

    async def _run_office(self, task_id: str, message: str):
        from reins.features.computer.desktop import get_desktop_backend
        from reins.features.workmode.artifacts import generate_demo_docx

        desktop = get_desktop_backend()

        yield WorkEvent(
            type="step_started",
            task_id=task_id,
            message="正在后台生成 Office 文档。",
        )

        path = generate_demo_docx(
            title="Community Operations Report",
            body=f"Task request: {message}",
        )

        yield WorkEvent(
            type="artifact_created",
            task_id=task_id,
            message="Word 文档已生成。",
            data={
                "path": str(path),
                "kind": "docx",
            },
        )

        open_result = desktop.open_file(str(path))

        yield WorkEvent(
            type="desktop_action",
            task_id=task_id,
            message="已打开文档供核验。",
            data=open_result,
        )

        screenshot_result = desktop.screenshot()

        yield WorkEvent(
            type="desktop_action",
            task_id=task_id,
            message="已保存桌面截图作为执行证据。",
            data=screenshot_result,
        )

    async def _run_browser(self, task_id: str, message: str):
        from reins.features.computer.desktop import get_desktop_backend

        desktop = get_desktop_backend()

        yield WorkEvent(
            type="browser_action",
            task_id=task_id,
            message="正在打开浏览器进行可见操作。",
            data={
                "input": message,
            },
        )

        result = desktop.open_url("https://example.com")

        yield WorkEvent(
            type="browser_action",
            task_id=task_id,
            message="浏览器已打开。",
            data=result,
        )

    async def _run_wechat(self, task_id: str, message: str):
        yield WorkEvent(
            type="confirmation_required",
            task_id=task_id,
            message="微信真实 UI 操作尚未在 MVP 中启用。后续需要 OCR、窗口确认和发送前确认。",
            data={
                "input": message,
            },
        )

    async def _run_desktop(self, task_id: str, message: str):
        from reins.features.computer.desktop import get_desktop_backend

        desktop = get_desktop_backend()

        yield WorkEvent(
            type="desktop_action",
            task_id=task_id,
            message="正在保存桌面截图。",
            data={
                "input": message,
            },
        )

        result = desktop.screenshot()

        yield WorkEvent(
            type="desktop_action",
            task_id=task_id,
            message="桌面截图已保存。",
            data=result,
        )