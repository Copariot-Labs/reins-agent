from __future__ import annotations

from typing import Any, Dict


class VisualExecutionEngine:
    """
    Executes ALL actions as visible operations.
    Browser, desktop, OCR, WeChat all go through here.
    """

    def __init__(self, browser=None, desktop=None, wechat=None):
        self.browser = browser
        self.desktop = desktop
        self.wechat = wechat

    # BROWSER (VISIBLE EXECUTION)
    async def open_url(self, url: str) -> Dict[str, Any]:
        page = await self.browser.new_page()
        await page.goto(url)

        screenshot = await page.screenshot(full_page=True)
        html = await page.content()

        return {
            "type": "browser",
            "action": "open_url",
            "url": url,
            "screenshot": screenshot,
            "html": html,
        }

    # DESKTOP (VISIBLE EXECUTION)
    async def capture_desktop(self) -> Dict[str, Any]:
        img = await self.desktop.capture()

        return {
            "type": "desktop",
            "action": "capture",
            "image": img,
        }

    # WECHAT (PLUGGABLE)
    async def wechat_action(self, action: str, payload: dict) -> Dict[str, Any]:
        result = await self.wechat.run(action, payload)

        return {
            "type": "wechat",
            "action": action,
            "result": result,
        }