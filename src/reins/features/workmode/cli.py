from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from reins.features.workmode.orchestrator import WorkModeOrchestrator


async def _run(message: str, mode: str) -> int:
    orchestrator = WorkModeOrchestrator()
    exit_code = 0

    async for event in orchestrator.run(message, mode=mode):
        print(event.to_json())

        if event.type == "task_failed":
            exit_code = 1

        if event.type == "task_finished" and event.data.get("status") == "failed":
            exit_code = 1

    return exit_code


def _doctor() -> int:
    from reins.api.home import get_reins_home
    from reins.features.workmode.artifacts import check_artifact_dependencies

    workmode_dir = get_reins_home() / "workmode"
    artifact_dir = workmode_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    dependencies = check_artifact_dependencies()
    ok = all(dependencies.values())
    result = {
        "ok": ok,
        "workmode_dir": str(workmode_dir),
        "artifact_dir": str(artifact_dir),
        "dependencies": dependencies,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reins workmode")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run")
    run_parser.add_argument("message", nargs="+")
    run_parser.add_argument("--mode", choices=["work", "demo", "headless"], default="work")

    sub.add_parser("doctor")

    args = parser.parse_args(list(argv or []))

    if args.command == "run":
        return asyncio.run(_run(" ".join(args.message).strip(), args.mode))

    if args.command == "doctor":
        return _doctor()

    parser.print_help()
    return 0
