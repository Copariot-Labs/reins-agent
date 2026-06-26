from __future__ import annotations

from reins.features.workmode.workers import run_worker


async def execute_visual_step(step, engine, state):

    # BROWSER FLOW
    if step.kind == "browser":
        return await engine.open_url(step.metadata["url"])

    # DESKTOP FLOW
    if step.kind == "desktop":
        return await engine.capture_desktop()

    # WECHAT FLOW
    if step.kind == "wechat":
        return await engine.wechat_action(
            step.metadata["action"],
            step.metadata
        )

    # BACKEND FALLBACK
    return await run_worker(step, state)