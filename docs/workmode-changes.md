# WorkMode Changes

Date: 2026-06-24

This document records the WorkMode changes made in the Reins project. The `community-ass-demo` project was used only as a reference for behavior and philosophy: backend-first execution, visible event streaming, persisted proof, and operator-friendly summaries. The implementation below is Reins-native.

## Goal

WorkMode should run a user task through the backend, produce a transparent live event stream, save the case history, and expose artifacts, sources, browser proof, desktop proof, failures, and final summary data in a shape that the CLI and web UI can both use.

## Philosophy-Based Work Order

Based on the community-operations philosophy, the Reins WorkMode sections should be built in this order:

1. Audit foundation: case storage, event streaming, artifacts, sources, and replay history.
2. Confirmation safety: block consequential actions until an operator can inspect the exact target, payload, risk, and verification requirements.
3. Visible presentation: open generated Office files and browser evidence for operator verification when mode allows visible actions.
4. Real WeChat UI path: focus/search WeChat, verify chat title with OCR, paste draft, confirm, send, and save screenshots.
5. Resident/staff workflows: richer case records, policy lookup, report/ledger generation, and handoff summaries.
6. Automated coverage: repeatable tests for office, backend, browser, desktop, OCR, WeChat, confirmation, and replay.

The first four sections are now implemented as the foundation. The remaining work is to harden the real UI paths on target machines and add automated coverage around them.

## Philosophy-Based Routing Rule

WorkMode now treats the project philosophy as the routing contract:

- Pure backend work stays in the backend.
- Generated Office files are created in the backend and presented visibly when mode allows.
- Links, domains, GitHub profiles, portals, browser pages, and web searches route to `browser_source`.
- Desktop screenshots, window checks, and desktop application launch/focus requests route to `desktop_capture`.
- WeChat and external send actions route through preparation plus confirmation before any real send path.
- Hermes planner output is repaired before execution when it conflicts with these rules, so a browser or desktop task cannot silently become fake `backend_only` success.

## Main Fixes

- Fixed broken planner-to-worker compatibility.
- Fixed browser and OCR worker runtime crashes.
- Restored event and artifact persistence.
- Restored UI-compatible final event data.
- Added real DOCX generation for Office/report workflows.
- Added browser proof capture with HTML and screenshot output.
- Added persisted case history and replay loading.
- Added WorkMode history/replay API endpoints and UI panel.
- Added structured confirmation blocking for consequential actions.
- Added a WorkMode confirmation panel for pending operator approvals.
- Added visible Office/browser presentation for non-headless WorkMode.
- Added approval/rejection commands and API endpoints for pending confirmations.
- Added a guarded macOS WeChat UI send path behind the confirmation gate.
- Added environment checks for browser/OCR dependencies.
- Switched WorkMode storage to respect `REINS_HOME`.
- Fixed planner routing so browser/profile/URL tasks do not fall back to fake `backend_only` completion.
- Added deterministic GitHub profile URL inference, including `visit github sshatil` -> `https://github.com/sshatil`.
- Added web-search URL inference, so search tasks can open browser source evidence.
- Added desktop-app intent detection, so app/window tasks route to desktop proof instead of browser or backend fallback.

## Worker Registry Changes

The old single-file worker module was split into a worker package:

- `src/reins/features/workmode/workers/registry.py`
- `src/reins/features/workmode/workers/backend/worker.py`
- `src/reins/features/workmode/workers/office/worker.py`
- `src/reins/features/workmode/workers/browser/worker.py`
- `src/reins/features/workmode/workers/desktop/worker.py`
- `src/reins/features/workmode/workers/ocr/worker.py`
- `src/reins/features/workmode/workers/wechat/worker.py`
- `src/reins/features/workmode/workers/confirmation/worker.py`

The registry now supports the step kinds emitted by the fallback planner:

- `backend_only`
- `backend_process`
- `result_present`
- `office_generate`
- `artifact_present`
- `browser_source`
- `desktop_capture`
- `ocr`
- `wechat_prepare`
- `confirmation_gate`

This fixes failures where plans emitted `artifact_present`, `backend_process`, or `result_present` but no worker was registered for those kinds.

## Orchestrator Changes

`src/reins/features/workmode/orchestrator.py` was updated to act more like a transparent work engine:

- All emitted events go through one `emit()` helper.
- Emitted events are persisted through `save_event()`.
- Case status is saved at start and finish.
- Worker results are harvested into a shared summary.
- Artifacts are saved with `save_artifact()`.
- Sources, screenshots, browser actions, desktop actions, OCR text, step results, and failures are collected.
- Failed steps emit `work.step.failed`.
- Hard failures emit `task_failed` before the final `task_finished`.
- Final `task_finished` data is flattened and also includes nested `summary`.

The final event now includes fields such as:

- `status`
- `mode`
- `execution_path`
- `policy`
- `plan`
- `artifacts`
- `sources`
- `desktop_actions`
- `screenshots`
- `ocr`
- `step_results`
- `failures`
- `artifact_count`
- `source_count`
- `desktop_action_count`
- `failure_count`
- `artifact_paths`
- `source_urls`
- `summary`
- `intake`

This keeps the payload compatible with the WorkMode web UI and still gives backend consumers a nested summary object.

## Office Artifact Flow

`office_generate` now creates a real DOCX file through:

- `src/reins/features/workmode/artifacts.py`
- `src/reins/features/workmode/workers/office/worker.py`

The generated artifact includes:

- `kind: "docx"`
- `type: "docx"`
- `title`
- `path`
- `summary`
- intake metadata
- step metadata

The `artifact_present` step records the latest artifact instead of failing.

## Browser Proof Flow

Browser work now uses Playwright's async API:

- `src/reins/features/workmode/workers/browser/engine.py`
- `src/reins/features/workmode/workers/browser/worker.py`

For a browser task, WorkMode can now:

- open a URL headlessly,
- save page HTML,
- save a PNG screenshot,
- emit `source_opened`,
- emit `browser_action`,
- emit `desktop_action`,
- include source and proof paths in the final summary.

Browser launch may require running outside the restricted sandbox on macOS because Chromium needs OS-level permissions.

In non-headless modes, browser work now launches a headed Playwright browser so the operator can see source evidence before the snapshot is saved. Headless mode still uses a non-visible browser.

Browser/profile/search tasks are now routed before execution through deterministic intent checks. If Hermes returns an incorrect `backend_only` step for a browser-like request, WorkMode repairs the plan to `browser_source`, keeps the execution path as `browser`, and uses the URL inferred from the original user message. This prevents commands such as `reins workmode run "visit github sshatil"` from silently reporting a fake backend success.

When the user asks for a web search and no explicit URL exists, WorkMode builds a browser search URL and captures browser proof from that source page.

The browser worker now emits:

- `browser_action`
- `desktop_action` when visible
- `source_opened`
- saved HTML
- saved PNG screenshot

## OCR Flow

The OCR worker crash was fixed by moving result-dependent context updates after OCR extraction.

OCR-specific work still requires the native `tesseract` binary. The Python packages alone are not enough.

## Storage Changes

WorkMode storage now respects Reins home configuration:

- `src/reins/features/workmode/db.py`
- `src/reins/features/workmode/proof.py`
- `src/reins/features/workmode/workers/browser/engine.py`

Instead of hardcoding `Path.home() / ".reins"`, these paths now use `get_reins_home()`. This allows tests and app runs to isolate data with `REINS_HOME`.

WorkMode stores:

- SQLite DB: `<REINS_HOME>/workmode.db`
- Office artifacts: `<REINS_HOME>/workmode/artifacts/`
- Browser proof: `<REINS_HOME>/workmode/browser/<case_id>/`
- Desktop proof: `<REINS_HOME>/workmode/proofs/<case_id>/`

Artifacts are now stored as full JSON payloads, not just raw text content. This keeps replay data useful for the UI because saved artifacts include fields such as `type`, `title`, `path`, `summary`, case metadata, and step metadata. Older artifact rows that only stored raw text are still decoded safely.

## History And Replay

The CLI now exposes persisted WorkMode cases:

- `reins workmode cases --limit 25`
- `reins workmode replay <case_id>`

The web server exposes the same data through:

- `GET /api/hermes/workmode/cases?limit=25`
- `GET /api/hermes/workmode/cases/:caseId`

The WorkMode UI now includes a History panel. It loads recent cases on mount, refreshes after a new run finishes, and lets the operator click a saved case to replay its event feed and final summary. This brings the Reins implementation closer to the reference demo behavior: live execution first, then inspectable saved history after the task is done.

## Confirmation Safety Flow

WeChat-style consequential actions now stop at a safe pending state instead of reporting false completion.

The flow is:

- `wechat_prepare` creates a structured dispatch draft with action, channel, target, draft message, case metadata, risk, and verification requirements.
- `confirmation_gate` converts that draft into a pending confirmation record.
- The orchestrator emits `confirmation_required`.
- The blocked step emits `work.step.blocked`.
- The final task status becomes `pending_confirmation`.
- The case is saved with `status: "pending_confirmation"` so history/replay can show the handoff state.
- The WorkMode UI displays pending confirmations in a dedicated panel with the target, action, risk, and copyable draft payload.
- The UI can approve or reject a pending confirmation.
- `reins workmode approve <case_id> <confirmation_id>` attempts the guarded execution path.
- `reins workmode reject <case_id> <confirmation_id>` records operator rejection and updates the case status.

This matches the philosophy requirement that real external sends, form submissions, and similar actions must be inspectable before they happen.

## Visible Presentation Flow

Non-headless WorkMode now presents key outputs instead of silently finishing:

- Office artifact presentation opens the generated file with the OS default app when visible actions are enabled.
- Browser source work opens a headed Chromium session when visible actions are enabled.
- Desktop app tasks open the requested application when visible actions are enabled, then capture desktop proof.
- Both flows record desktop/browser action metadata for the UI.
- Best-effort screenshots are captured after visible presentation when the operating system allows it.

If the OS blocks window control or screenshots, WorkMode keeps the artifact/source path in the audit trail and records the presentation failure as action metadata.

## WeChat Approval Path

Approved WeChat sends now go through a guarded UI path:

- activate WeChat on macOS,
- search for the target contact,
- capture a screenshot,
- run OCR against the screenshot,
- verify the target appears in OCR text,
- paste the prepared message,
- send only after verification,
- capture post-send proof.

If activation, clipboard access, screenshot capture, OCR, or target verification fails, the message is not sent and the case remains inspectable.

## Doctor Checks

`workmode doctor` now checks:

- `python-docx`
- `playwright`
- `playwright-chromium`
- `pillow`
- `pytesseract`
- native `tesseract`

At the time of verification, Chromium was available, but native `tesseract` was still missing.

## Dependencies Added

`pyproject.toml` now includes:

- `playwright>=1.49`
- `pillow>=10.0`
- `pytesseract>=0.3`

These support browser proof and OCR-related WorkMode steps.

## Verified Scenarios

The following flows were verified:

- Office/report:
  `reins workmode run "generate an operations report" --mode headless`

- Backend with presentation:
  `reins workmode run "summarize this resident request" --mode headless`

- Case history:
  `reins workmode cases --limit 5`

- Case replay:
  `reins workmode replay <case_id>`

- Confirmation blocking:
  `reins workmode run "send wechat update to property manager about broken elevator" --mode headless`

- Confirmation rejection:
  `reins workmode reject <case_id> <confirmation_id>`

- Confirmation approval:
  `reins workmode approve <case_id> <confirmation_id>`

- Browser proof:
  `reins workmode run "open browser portal https://example.com" --mode headless`

Browser proof was verified outside the restricted sandbox. It produced:

- `source_opened`
- `browser_action`
- `desktop_action`
- saved HTML file
- saved PNG screenshot
- completed final summary

SQLite persistence was also verified:

- Office saved case, events, and artifact.
- Backend saved case and events.
- Browser saved case and events, plus proof files.
- Fresh Office replay returned full artifact metadata, including the generated DOCX path.
- WeChat-style dispatch saved a `pending_confirmation` case with a replayable confirmation payload.
- Confirmation rejection updated the case status to `rejected`.
- Office replay kept a single generated DOCX artifact after presentation.

## Verification Commands

These checks passed:

```bash
.venv/bin/python -m compileall -q src/reins/features/workmode
npx vue-tsc -b
npx tsc --noEmit -p packages/server/tsconfig.json
npm test -- i18n-coverage.test.ts
npm run build
```

`npm run build` completed with the existing large chunk warning.

## Remaining Work

- Install native `tesseract` before relying on OCR tasks.
- Configure Hermes provider/model if Hermes planning should be used instead of fallback planning.
- Validate visible Office/browser presentation on the target desktop outside the sandbox.
- Validate the real WeChat UI/OCR/send path on the target macOS account with Accessibility, screen recording, and Tesseract configured.
- Add richer task-specific workers instead of placeholder backend text processing.
- Add automated tests for each execution path:
  office, backend, browser, desktop, OCR, WeChat, confirmation.

## Current Direction

The WorkMode section is now aligned with the reference project's philosophy:

- backend does the real work,
- frontend observes live progress,
- every important action emits an event,
- proof and artifacts are saved,
- final output is structured and inspectable,
- failures are visible instead of hidden.

The next part should harden these UI paths on the real target machine, then add automated tests and richer resident/staff workflow workers.
