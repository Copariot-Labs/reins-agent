from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from reins.features.workmode.orchestrator import WorkModeOrchestrator


async def _run(message: str, mode: str) -> int:
    orchestrator = WorkModeOrchestrator()

    async for event in orchestrator.run(message, mode=mode):
        print(event.to_json())

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reins workmode")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run")
    run_parser.add_argument("message")
    run_parser.add_argument("--mode", choices=["work", "demo"], default="work")

    sub.add_parser("doctor")

    args = parser.parse_args(list(argv or []))

    if args.command == "run":
        return asyncio.run(_run(args.message, args.mode))

    if args.command == "doctor":
        from reins.api.home import get_reins_home

        workmode_dir = get_reins_home() / "workmode"
        artifact_dir = workmode_dir / "artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        print(f"WorkMode OK: {workmode_dir}")
        print(f"Artifacts: {artifact_dir}")
        return 0

    parser.print_help()
    return 0