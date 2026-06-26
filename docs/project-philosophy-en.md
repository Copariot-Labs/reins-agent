# Community Operations Agent Project Philosophy

## One-sentence definition

This project is not a traditional `computer use` automation tool. It is an **"agentic backend execution + transparent frontend behavior"** system.

Its goal is not to mechanically simulate every mouse and keyboard action. Instead:

- do everything that can be handled in the backend in the backend
- expose the actions that people need to see in the frontend
- use real `computer use` only when there is no stable API or backend path
- make it easy for leaders, users, and handoff engineers to understand what the system is doing, where it is, and what it produced

## 1.1 Additional goal: serving residents and staff

This Agent is not only a demo system or an automation utility. It is intended to be an entry point for daily community work.

It should serve two groups:

- Residents: answer questions, understand reports, ask for missing details, record tickets, and provide progress updates
- Staff: look up references, summarize cases, prepare ledgers, draft reports, and sync notifications

When a resident uses the Agent to ask for information or report a problem, the system should do more than return a single answer:

- answer whatever it can answer immediately
- turn actionable content into a ticket or case record
- explain the next handling step when coordination is needed
- leave visible traces in both the frontend and the desktop actions

For staff, it should behave like a community assistant for routine operations:

- look up local references and policy basis
- summarize the issue and suggested handling
- generate Word / Excel records
- present the result for colleagues to verify

---

## 1. What this project actually is

This project is a community-operations Agent platform for real business workflows. It has three core layers:

1. Understand the task
2. Execute in the backend
3. Present visible behavior in the frontend

It is neither a black box that only prints results, nor a screen recorder that blindly replays human input.

The design is:

- **the Agent does the real reasoning and work in the backend**
- **the desktop UI only exposes the important actions and outputs**
- **users see a transparent work process, not just a silent final result**

So “transparency” here is not a slogan. It is a design principle.

---

## 2. Why we separate demo mode and work mode

### Demo mode

Demo mode is for executives, clients, and external audiences.

Its goal is not maximum throughput. Its goal is to make it obvious that the system:

- understands the problem
- really operates desktop software
- completes the task step by step
- provides visual feedback at each key stage

Demo mode is closer to a stage performance: steady pacing, complete motions, and clear narrative flow.

### Work mode

Work mode is for real internal task handling.

It is neither a fixed theatrical script nor a silent black box.

Its goals are:

- really do the work
- really produce outputs
- really remain transparent
- really be handoff-friendly

Compared with demo mode, work mode cares more about practical throughput, but it still keeps the process visible so operators know what the Agent is doing.

---

## 3. The core principle of work mode

The core of work mode is not “every step must be explicit computer use.”

The real principle is:

```text
Backend processing + real desktop actions + SSE narration + final artifact presentation
```

Break that down:

### Backend processing

Anything that can be completed in the backend should be completed in the backend first, for example:

- information retrieval
- document generation
- content summarization
- artifact packaging
- file naming and persistence

These tasks do not need to be forced into mouse-by-mouse UI interactions.

### Real desktop actions

If the user needs to see the system working, we expose the key actions in the desktop UI, for example:

- opening a browser
- opening Word / Excel
- browsing web pages
- scrolling through content
- opening source pages for verification
- moving windows to specific positions

What is shown is the behavior trace, not the full internal computation.

### SSE narration

The frontend must stream task status, action explanations, artifact paths, and failure reasons.

In other words, the UI should show not only the result, but also the explanation.

### Final artifact presentation

Work mode is not allowed to end with a single “done” log line.

It must clearly show:

- how many files were generated
- where each file is located
- what type each file is
- which sources contributed to the conclusion

---

## 4. Why this is not traditional computer use

Traditional `computer use` usually means:

- the model simulates mouse and keyboard actions step by step
- all actions happen directly through the UI
- the execution path itself is the main mechanism

That is not our design.

Our approach is:

1. First decide whether the task can be handled in the backend
2. If yes, do it in the backend
3. If the user needs to see the process, map the key steps to visible desktop behavior
4. Only when there is no stable API or automation path do we use real computer use

So `computer use` is only one capability of the system, not the system definition itself.

In short:

- **not every task should be executed like a human sitting at the keyboard**
- **the system should behave like a reliable business executor**
- **automate when possible, expose when necessary, emulate by hand only when required**

---

## 5. When to use backend automation, and when real computer use is required

### Best suited for backend automation

These tasks can usually be completed through code, files, browser automation, or local document processing:

- searching and summarizing information
- generating Word / Excel files
- writing and saving files
- archiving outputs
- consolidating multi-source information
- producing structured reports

The rule is:

- finish it in the backend first
- then present it in the frontend

Example:

- the backend already generated a Word document
- the frontend should open that Word file, display it in a fixed location for a few seconds, and then minimize or close it

This avoids wasting time and avoids the feeling that the system “silently completed everything with no proof.”

### Requires real computer use

Some systems have no usable API, or the API is not enough. In those cases we must interact with the real interface:

- WeChat
  - there is no stable official automation API for our use case
  - OCR, screenshots, window control, and keyboard/mouse simulation are required for sending and receiving messages

- websites that require login
  - for example job boards, internal message systems, and some government or enterprise portals
  - they require real browser login, page navigation, form filling, and confirmation

These cases cannot be treated as “the backend already handled it,” because they are fundamentally UI-driven systems.

So real computer use is not for show. It exists to fill the gap left by missing interfaces.

---

## 6. The right technical stack for real computer use

Real computer use should not depend on a single tool. It should be layered.

Below is the stack that fits this project.

### 6.1 Orchestration layer

Responsible for task understanding, step planning, state sync, and cancellation.

Suggested / existing components:

- Hermes Agent
- LLM router
- task orchestrator
- SSE event bus

Responsibilities:

- parse user intent
- choose the execution path
- decide whether to enter browser / WeChat / Office / headless flow
- emit readable step explanations

### 6.2 Browser layer

Responsible for web search, page interaction, login-based sites, and source verification.

Suggested / existing components:

- `browser-use`
- Playwright
- Chromium / Chrome / Edge

Typical usage:

- `browser-use` for candidate discovery and page-level interaction
- Playwright for deterministic operations, deep reading, and screenshots
- real browser sessions for login-required websites

This layer is suitable for:

- search engine workflows
- internal message systems
- form submission
- long pages that require scrolling

### 6.3 Desktop control layer

Responsible for opening, activating, moving, resizing, and typing into real desktop windows.

Suggested / existing components:

- `wmctrl`
- `xdotool`
- `xclip`
- `pyautogui`
- `pyperclip`

Responsibilities:

- activate windows
- copy and paste text
- keyboard input
- mouse clicking
- window placement

On Ubuntu, this layer is the foundation for visible WeChat and Office behavior.

### 6.4 Vision / verification layer

Responsible for screenshots, OCR, UI-state checks, and failure validation.

Suggested / existing components:

- `mss`
- `opencv-python-headless`
- `Pillow`
- `pytesseract`

Responsibilities:

- capture screens
- crop regions
- OCR chat titles, page text, and button states
- validate whether “looks successful” is actually successful

Examples:

- run OCR on the chat title before sending a WeChat message
- use screenshots after browser search to confirm that the source page actually opened

### 6.5 Office layer

Responsible for generating and visibly presenting Word / Excel artifacts.

Suggested / existing components:

- `python-docx`
- `openpyxl`
- LibreOffice
- `pyautogui` / `xdotool` for visible interaction

Responsibilities:

- generate documents in the backend
- open them in the foreground
- keep them visible long enough for verification

### 6.6 State / audit layer

Responsible for traceability, artifact tracking, and replayable audit history.

Suggested / existing components:

- FastAPI
- SQLite
- logging
- `logs/screenshots/`
- `logs/actions/`
- `data/demo.db`

Responsibilities:

- record what happened at each step
- preserve sources, paths, screenshots, and summaries
- give the next engineer evidence for debugging and handoff

### 6.7 Frontend presentation layer

Responsible for translating backend activity into a visible working surface.

Suggested / existing components:

- `pywebview`
- SSE text streaming
- desktop window layout management

Responsibilities:

- show task status, action explanations, and artifact paths on the left side
- show real desktop window behavior on the right side
- return to the frontend for the final summary

---

## 7. The right way to make “transparency” visible

Transparency does not mean “slow-motion every single step.”

Transparency also does not mean “only show a final result and pretend the process never happened.”

The correct pattern is:

- finish the real work in the backend first
- turn the key actions into visible desktop behavior
- use SSE to explain why each action exists
- show the final artifacts and paths

Typical examples:

### Word / Excel

If the backend already generated the file, do not invent a fake editing process.

Instead:

- open Word / Excel
- move it to the designated position
- display it for a few seconds
- then minimize or close it

The user sees both the result and proof that it is a real artifact.

### Web search

If the backend already found the answer, do not limit the UI to a single log line.

Instead:

- open the browser
- open each source page
- scroll through the content
- show where the conclusion came from
- then close or return to the frontend

The user should see evidence of actual research, not just a model saying it researched something.

### WeChat

WeChat is not a backend API system, so it must be handled as real UI work.

The correct pattern is:

- focus the window
- search for the contact
- confirm the chat title with OCR
- enter the message
- send it
- save the trace

This kind of action cannot rely on backend reasoning alone.

---

## 8. The decision checklist for a handoff engineer

When deciding whether a function design fits this project, ask:

1. Can this be completed in the backend?
2. If yes, what should the frontend show?
3. Does this step truly require the real UI?
4. Does this step need OCR, screenshots, or window confirmation?
5. After execution, can the user clearly tell where the artifact lives?

If these questions cannot be answered cleanly, the design is probably not work-mode-shaped enough.

---

## 9. The most important development principles

### Principle 1

Do not turn work mode into a pure black box.

If the system only tries to “finish,” but does not show the process, it violates the core philosophy.

### Principle 2

Do not merge demo mode and work mode into one thing.

Demo mode is for leaders. Work mode is for real task execution. Their goals are different.

### Principle 3

Do not force computer use where backend automation is enough.

Real computer use is only for scenarios that truly lack a stable interface or automation path.

### Principle 4

The frontend must explain the process.

It should not only say “success.” It should show:

- what was done
- why it was done
- what the artifact is
- where the artifact is

### Principle 5

Desktop actions must be verifiable.

For WeChat, login sites, and Office workflows, the result must be provable from screenshots, OCR, window state, or logs.

---

## 10. A short project summary you can reuse

If you need a more formal one-paragraph description, you can use this:

> The core philosophy of this project is not traditional computer use, but “agentic backend execution + transparent frontend behavior.” The system prioritizes real task execution in the backend and exposes key actions, status, source evidence, and final artifacts through SSE and desktop windows. For scenarios like WeChat or login-required websites that do not have stable APIs, it falls back to real computer use to complete the UI interaction. This preserves efficiency, visibility, and handoff maintainability at the same time.

---

## 11. Recommended reading order

For a new handoff engineer, read in this order:

1. `README.md`
2. `docs/工作模式.md`
3. `docs/演示计划.md`
4. `docs/计划.md`
5. This document

That sequence gives you the project overview first, then the mode split, then the design rationale.
