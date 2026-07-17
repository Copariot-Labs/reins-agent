from __future__ import annotations

import argparse
import json
import sys

from collections.abc import Sequence
from typing import Any

from reins.features.presentation.doctor import run_presentation_doctor
from reins.features.presentation.models import PresentationRequest
from reins.features.presentation.service import PresentationService


def _print_json(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False))


def _read_request(args: argparse.Namespace) -> PresentationRequest:
    if args.request_json:
        raw = args.request_json
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        raise ValueError(
            "Presentation request JSON is required through stdin or --request-json."
        )

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Presentation request JSON must be an object.")

    return PresentationRequest.model_validate(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reins presentation",
        description="Create and inspect Reins presentation jobs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser("submit")
    submit.add_argument("--request-json")
    submit.add_argument(
        "--foreground",
        action="store_true",
        help="Run the job synchronously instead of starting a worker.",
    )

    run = subparsers.add_parser("run")
    run.add_argument("job_id")

    status = subparsers.add_parser("status")
    status.add_argument("job_id")

    plan = subparsers.add_parser("plan")
    plan.add_argument("job_id")

    jobs = subparsers.add_parser("list")
    jobs.add_argument("--limit", type=int, default=25)

    subparsers.add_parser("doctor")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.command == "doctor":
            _print_json(run_presentation_doctor())
            return 0

        service = PresentationService()

        if args.command == "submit":
            request = _read_request(args)
            if args.foreground:
                result = service.create_job(request)
                _print_json(result)
                return 0 if result.success else 1

            state = service.submit_job(request)
            _print_json(state)
            return 0 if state.error is None else 1

        if args.command == "run":
            result = service.run_job(args.job_id)
            _print_json(result)
            return 0 if result.success else 1

        if args.command == "status":
            _print_json(service.get_job_state(args.job_id))
            return 0

        if args.command == "plan":
            _print_json(service.get_job_plan(args.job_id))
            return 0

        if args.command == "list":
            states = service.storage.list_job_states(limit=args.limit)
            _print_json(
                {
                    "jobs": [state.model_dump(mode="json") for state in states]
                }
            )
            return 0

    except Exception as exc:
        _print_json({"error": str(exc)})
        return 1

    parser.error(f"Unknown presentation command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
