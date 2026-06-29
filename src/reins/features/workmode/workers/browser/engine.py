from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reins.api.home import get_reins_home
from reins.features.workmode.workers.browser.config import BrowserLaunchConfig, resolve_browser_launch_config

MAX_ERROR_CHARS = 700


@dataclass
class BrowserSession:
    context: Any
    browser: Any
    config: BrowserLaunchConfig


def get_browser_dir(case_id: str) -> Path:
    path = get_reins_home() / "workmode" / "browser" / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _error_text(exc: Exception) -> str:
    text = str(exc).strip()
    if len(text) <= MAX_ERROR_CHARS:
        return text
    return f"{text[:MAX_ERROR_CHARS].rstrip()}... [truncated]"


async def open_browser_session(
    playwright: Any,
    *,
    visible: bool,
    viewport: dict[str, int] | None = None,
    user_agent: str | None = None,
    persistent: bool | None = None,
) -> BrowserSession:
    config = resolve_browser_launch_config(visible=visible, persistent=persistent)
    launch_options = config.launch_options()

    if config.persistent:
        if not config.profile_dir:
            raise RuntimeError("Persistent browser profile directory is not configured.")
        Path(config.profile_dir).mkdir(parents=True, exist_ok=True)
        context_options: dict[str, Any] = {}
        if viewport is not None:
            context_options["viewport"] = viewport
        if user_agent is not None:
            context_options["user_agent"] = user_agent
        context = await playwright.chromium.launch_persistent_context(
            config.profile_dir,
            **launch_options,
            **context_options,
        )
        return BrowserSession(context=context, browser=None, config=config)

    browser = await playwright.chromium.launch(**launch_options)
    context_options: dict[str, Any] = {}
    if viewport is not None:
        context_options["viewport"] = viewport
    if user_agent is not None:
        context_options["user_agent"] = user_agent
    context = await browser.new_context(**context_options)
    return BrowserSession(context=context, browser=browser, config=config)


async def close_browser_session(session: BrowserSession) -> None:
    await session.context.close()
    if session.browser is not None:
        await session.browser.close()


async def capture_page_snapshot(
    url: str,
    case_id: str,
    *,
    visible: bool = False,
    hold_ms: int = 1500,
) -> dict[str, Any]:
    """
    Browser snapshot.

    Requires:
      pip install playwright
      playwright install
    """

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": f"Playwright unavailable: {exc}",
            "url": url,
        }

    output_dir = get_browser_dir(case_id)
    ts = _timestamp()

    screenshot_path = output_dir / f"page-{ts}.png"
    html_path = output_dir / f"page-{ts}.html"

    try:
        async with async_playwright() as p:
            session: BrowserSession | None = None
            try:
                session = await open_browser_session(
                    p,
                    visible=visible,
                    viewport={"width": 1366, "height": 900},
                )
                page = await session.context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(max(hold_ms, 500))

                html_path.write_text(await page.content(), encoding="utf-8")
                await page.screenshot(path=str(screenshot_path), full_page=True)

                title = await page.title()
                if visible and hold_ms > 0:
                    await page.wait_for_timeout(hold_ms)
            finally:
                if session is not None:
                    await close_browser_session(session)

        return {
            "ok": True,
            "kind": "browser_snapshot",
            "url": url,
            "title": title,
            "screenshot": str(screenshot_path),
            "html": str(html_path),
            "visible": visible,
            "browser_config": session.config.to_dict(),
        }

    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": _error_text(exc),
            "url": url,
        }
