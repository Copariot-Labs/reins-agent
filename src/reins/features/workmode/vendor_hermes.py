from __future__ import annotations

import contextlib
import io
import json
import sys
from typing import Any


class VendorHermesError(Exception):
    pass


def _extract_json_object(text: str) -> dict[str, Any]:
    """
    Hermes may return pure JSON or JSON surrounded by text.
    This extracts the first JSON object safely.
    """
    text = text.strip()

    if not text:
        raise VendorHermesError("Hermes returned empty output.")

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
        raise VendorHermesError("Hermes returned JSON, but not a JSON object.")
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise VendorHermesError(
            f"Could not find JSON object in Hermes output: {text[:300]}"
        )

    candidate = text[start : end + 1]

    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise VendorHermesError(
            f"Could not parse JSON object from Hermes output: {exc}"
        ) from exc

    if not isinstance(value, dict):
        raise VendorHermesError("Extracted Hermes JSON is not an object.")

    return value


def _build_planner_prompt(
    message: str,
    *,
    mode: str,
    intake: dict[str, Any] | None,
) -> str:
    intake = intake or {}

    return f"""
You are Hermes Agent acting as the planner for Reins WorkMode.

Your job is ONLY to produce a valid WorkMode plan.

Return ONLY valid JSON.
Do not include markdown.
Do not include explanations.
Do not wrap the JSON in code fences.

User task:
{message}

WorkMode:
{mode}

Resident intake:
{json.dumps(intake, ensure_ascii=False)}

Return a JSON object with this exact shape:

{{
  "id": "short-plan-id",
  "intent": "user intent",
  "summary_for_user": "brief plan summary",
  "steps": [
    {{
      "id": "step-id",
      "kind": "backend_only",
      "title": "Step title",
      "worker": "workmode.backend",
      "description": "What this step does",
      "visible_action": false,
      "requires_confirmation": false,
      "expected_artifacts": [],
      "depends_on": [],
      "metadata": {{}}
    }}
  ],
  "risk_flags": [],
  "version": 1
}}

Allowed step kinds:
- backend_only
- office_generate
- artifact_present
- browser_source
- desktop_capture
- ocr
- wechat_prepare
- confirmation_gate

Rules:
- If the task is a resident repair, complaint, safety issue, or service request, prefer office_generate.
- If the task includes an explicit URL, domain, link, website, portal, GitHub profile, browser page, or web source, use browser_source and put the target in step.metadata.url when known.
- If the user asks to search, research, look up, or Google something on the web, use browser_source so source evidence can be shown.
- If the task requires a screenshot, desktop proof, window capture, app launch, app focus, or opening a desktop application, use desktop_capture and put the application name in step.metadata.app_name when known.
- If the task asks for WeChat message preparation, use wechat_prepare followed by confirmation_gate.
- If the task is simple text processing, use backend_only.
- Prefer backend_only only when no browser, Office, desktop, OCR, or WeChat evidence is needed.
- Keep the plan short.
- Do not invent unsupported step kinds.
- Do not execute the task.
- Only plan the task.
- Return JSON only.
""".strip()


def call_vendor_hermes_planner(
    message: str,
    *,
    mode: str,
    intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Connect Reins WorkMode to vendor Hermes through the existing Reins wrapper.

    This does not modify vendor/hermes-agent.

    Flow:
    - prepare Reins/Hermes environment
    - bootstrap vendor Hermes
    - call Hermes chat through run_hermes
    - capture stdout
    - extract JSON plan
    """

    try:
        from reins.compat.env import prepare_env
        from reins.compat.bootstrap import apply_bootstrap
        from reins.compat.cli import run_hermes
    except Exception as exc:
        raise VendorHermesError(f"Could not import Reins/Hermes wrapper: {exc}") from exc

    try:
        prepare_env()
    except Exception as exc:
        raise VendorHermesError(f"prepare_env failed: {exc}") from exc

    try:
        apply_bootstrap()
    except Exception as exc:
        raise VendorHermesError(f"Hermes bootstrap failed: {exc}") from exc

    prompt = _build_planner_prompt(
        message,
        mode=mode,
        intake=intake,
    )

    old_argv = sys.argv[:]

    stdout = io.StringIO()
    stderr = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = run_hermes(["chat", prompt])

    except SystemExit as exc:
        exit_code = int(exc.code or 0)

    except Exception as exc:
        raise VendorHermesError(f"Hermes execution failed: {exc}") from exc

    finally:
        sys.argv = old_argv

    out = stdout.getvalue()
    err = stderr.getvalue()

    if exit_code != 0:
        raise VendorHermesError(
            f"Hermes exited with code {exit_code}. stderr={err[:500]} stdout={out[:500]}"
        )

    return _extract_json_object(out)
