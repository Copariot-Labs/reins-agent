from __future__ import annotations

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.url_resolver import infer_url_from_message
from reins.features.workmode.workers.browser.engine import capture_page_snapshot
from reins.features.workmode.workers.registry import registry
from reins.features.workmode.workers.types import WorkerResult


def _resolve_url(step: WorkStep, state: WorkExecutionState) -> str:
    inferred = infer_url_from_message(state.message)
    if inferred:
        return inferred

    raw = step.metadata.get("url") or state.message

    text = str(raw).strip()

    for part in text.split():
        if part.startswith("http://") or part.startswith("https://"):
            return part

    if text.startswith("http://") or text.startswith("https://"):
        return text

    return "https://example.com"


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    intake = state.scratch.get("intake", {})
    case_id = intake.get("case_id") or state.task_id
    url = _resolve_url(step, state)
    visible = bool(step.visible_action and state.mode_policy.visible_actions)

    result = await capture_page_snapshot(
        url=url,
        case_id=case_id,
        visible=visible,
        hold_ms=max(state.mode_policy.key_action_preview_ms, 1500 if visible else 500),
    )

    context_update = {
        "last_url": result.get("url"),
        "page_title": result.get("title"),
    }

    screenshots: list[str] = []

    if result.get("ok") and result.get("screenshot"):
        screenshots.append(str(result["screenshot"]))

    sources = []

    if result.get("ok"):
        sources.append(
            {
                "type": "browser",
                "url": result.get("url"),
                "title": result.get("title"),
                "html": result.get("html"),
                "screenshot": result.get("screenshot"),
            }
        )

    browser_action = {
        "kind": "open_browser_source",
        "url": result.get("url") or url,
        "title": result.get("title"),
        "visible": visible,
        "screenshot": result.get("screenshot"),
        "html": result.get("html"),
        "ok": bool(result.get("ok")),
        "error": result.get("error"),
    }

    return {
        "ok": bool(result.get("ok")),
        "worker": "browser_source",
        "step_id": step.id,
        "browser": result,
        "screenshots": screenshots,
        "sources": sources,
        "browser_actions": [browser_action],
        "desktop_actions": [browser_action] if visible else [],
        "context": context_update,
    }


registry.register("browser_source", run)
