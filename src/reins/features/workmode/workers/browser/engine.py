from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reins.api.home import get_reins_home

MAX_ERROR_CHARS = 700


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
            browser = await p.chromium.launch(headless=not visible)
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(max(hold_ms, 500))

            html_path.write_text(await page.content(), encoding="utf-8")
            await page.screenshot(path=str(screenshot_path), full_page=True)

            title = await page.title()
            if visible and hold_ms > 0:
                await page.wait_for_timeout(hold_ms)
            await browser.close()

        return {
            "ok": True,
            "kind": "browser_snapshot",
            "url": url,
            "title": title,
            "screenshot": str(screenshot_path),
            "html": str(html_path),
            "visible": visible,
        }

    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": _error_text(exc),
            "url": url,
        }
