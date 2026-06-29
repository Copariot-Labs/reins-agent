from __future__ import annotations

from reins.features.workmode.executor import WorkExecutionState
from reins.features.workmode.planner import WorkStep
from reins.features.workmode.url_resolver import (
    infer_search_query_from_message,
    infer_url_from_message,
    is_web_search_intent,
)
from reins.features.workmode.workers.browser.engine import capture_page_snapshot
from reins.features.workmode.workers.browser.research import run_browser_research
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


def _should_research(step: WorkStep, state: WorkExecutionState) -> bool:
    if step.metadata.get("research") is True:
        return True
    if step.metadata.get("research") is False:
        return False
    return is_web_search_intent(state.message)


def _research_query(step: WorkStep, state: WorkExecutionState) -> str:
    query = str(step.metadata.get("query") or "").strip()
    if query:
        return query
    return infer_search_query_from_message(state.message)


async def _run_research(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    intake = state.scratch.get("intake", {})
    case_id = str(intake.get("case_id") or state.task_id)
    visible = bool(step.visible_action and state.mode_policy.visible_actions)
    query = _research_query(step, state)

    result = await run_browser_research(
        query=query,
        case_id=case_id,
        visible=visible,
        max_sources=int(step.metadata.get("max_sources") or 3),
        hold_ms=max(state.mode_policy.key_action_preview_ms, 1500 if visible else 500),
    )

    search_page = result.get("search_page") if isinstance(result.get("search_page"), dict) else {}
    screenshots = [
        str(path)
        for path in result.get("screenshots", [])
        if path
    ]
    sources = [
        {
            "type": "browser_research",
            "url": source.get("url"),
            "title": source.get("title"),
            "summary": source.get("summary"),
            "screenshot": source.get("screenshot"),
            "html": source.get("html"),
            "rank": source.get("rank"),
            "relevance_score": source.get("relevance_score"),
            "key_facts": source.get("key_facts"),
            "published": source.get("published"),
        }
        for source in result.get("sources", [])
        if isinstance(source, dict)
    ]

    browser_actions = [
        {
            "kind": "browser_research_search",
            "title": "Search web sources",
            "query": query,
            "url": result.get("search_url"),
            "visible": visible,
            "screenshot": search_page.get("screenshot"),
            "html": search_page.get("html"),
            "ok": bool(result.get("ok")),
            "source_count": len(sources),
            "browser_config": search_page.get("browser_config"),
            "error": result.get("error"),
        }
    ]

    for source in sources:
        browser_actions.append({
            "kind": "browser_research_source",
            "title": source.get("title") or "Research source",
            "url": source.get("url"),
            "visible": visible,
            "screenshot": source.get("screenshot"),
            "html": source.get("html"),
            "ok": True,
            "rank": source.get("rank"),
            "relevance_score": source.get("relevance_score"),
            "browser_config": search_page.get("browser_config"),
        })

    return {
        "ok": bool(result.get("ok")),
        "worker": "browser_source",
        "step_id": step.id,
        "browser": search_page or {
            "ok": bool(result.get("ok")),
            "kind": "browser_research",
            "url": result.get("search_url"),
            "title": "Browser research",
            "visible": visible,
            "error": result.get("error"),
        },
        "research": result,
        "artifact": result.get("artifact"),
        "screenshots": screenshots,
        "sources": sources,
        "browser_actions": browser_actions,
        "desktop_actions": browser_actions if visible else [],
        "context": {
            "last_url": result.get("search_url"),
            "search_query": query,
            "research_status": result.get("status"),
            "research_summary": result.get("briefing"),
            "source_count": len(sources),
            "browser_config": search_page.get("browser_config"),
        },
    }


async def run(step: WorkStep, state: WorkExecutionState) -> WorkerResult:
    if _should_research(step, state):
        return await _run_research(step, state)

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
        "browser_config": result.get("browser_config"),
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
