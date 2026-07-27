# Reins Agent

Reins Agent is a local-first personal agent product built on top of the upstream Hermes Agent runtime. Reins owns the product wrapper, local data home, Finance tools, WeCom work-order tools, artifacts, presentations, and Web UI integration. Hermes remains the upstream core for chat, models, memory, skills, gateway, and the agent loop.

`vendor/hermes-agent/` is upstream source. Do not patch it for Reins product work unless you are intentionally updating the vendored runtime.

## Repository

```text
.
├── src/reins/                  # Reins Python package and CLI
│   ├── compat/                 # Hermes compatibility, bootstrap, env, web launcher
│   └── features/               # Reins-owned product features
│       ├── finance/            # Local finance parser, SQLite, reports, CSV, plugin
│       ├── wecom/              # WeCom work orders, ticket API polling, Excel ledger
│       ├── artifacts/          # Chat-triggered Office/text artifact creation
│       └── presentation/       # Presentation jobs and engines
├── web/                        # Vue/Koa Web UI
├── scripts/                    # Local helper scripts
├── external/                   # Optional local engines/assets
├── vendor/hermes-agent/        # Vendored Hermes runtime
└── pyproject.toml
```

## Requirements

- Python 3.11+
- `uv`
- Node.js 23+
- npm
- Git submodules initialized

## Setup

macOS/Linux:

```bash
git clone https://github.com/Copariot-Labs/reins-agent.git
cd reins-agent
git submodule update --init --recursive

uv venv
source .venv/bin/activate
uv pip install -e vendor/hermes-agent
uv pip install -e .

cd web
npm install
cd ..
```

Windows PowerShell:

```powershell
git clone https://github.com/Copariot-Labs/reins-agent.git
cd reins-agent
git submodule update --init --recursive

uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -e vendor/hermes-agent
uv pip install -e .

cd web
npm install
cd ..
```

If PowerShell blocks venv activation, run this in the same terminal and activate again:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Check the install:

```bash
reins version
reins about
reins debug-env
```

## Data And Env

Default Reins data homes:

```text
macOS/Linux: ~/.reins
Windows:     %LOCALAPPDATA%\reins
```

Core paths:

```text
<REINS_HOME>/finance/finance.sqlite
<REINS_HOME>/wecom/wecom.sqlite
<REINS_HOME>/wecom/records.xlsx
<REINS_HOME>/artifacts/
<REINS_HOME>/presentations/
<REINS_HOME>/web-ui/
<REINS_HOME>/plugins/
<REINS_HOME>/.env
```

`reins` sets `HERMES_HOME` to `REINS_HOME` so Hermes data stays inside the Reins product home. `REINS_HOME` and `HERMES_HOME` both support absolute paths, `~`, `$VAR`, `${VAR}`, and Windows `%VAR%` expansion.

## CLI Basics

```bash
reins --help
reins chat
reins chat "hello"
reins doctor
reins model
reins tools
reins config
reins sessions
```

Reins-owned commands:

```bash
reins finance --help
reins wecom --help
reins artifacts --help
reins presentation --help
reins web
reins migrate hermes
reins update
reins debug-env
```

## Web UI

Start the development Web UI through Reins:

```bash
reins web
```

Helper scripts:

```bash
scripts/start-reins-web.sh
```

```powershell
.\scripts\start-reins-web.ps1
```

Direct web development:

```bash
cd web
npm run dev
npm run build
npm test
```

Default development ports:

```text
backend:  8647
frontend: 8649
```

## Finance CLI

```bash
reins finance doctor
reins finance parse "今天买咖啡 28"
reins finance add "今天买咖啡 28"
reins finance list
reins finance list --month 2026-06
reins finance report
reins finance export csv
reins finance export csv --output ~/Desktop/reins-finance.csv
reins finance install-plugin
reins plugins enable reins-finance
```

Windows export example:

```powershell
reins finance export csv --output "$env:USERPROFILE\Desktop\reins-finance.csv"
```

## WeCom CLI

The WeCom feature handles community work-order intake, local SQLite records, staff-facing Excel export, responsible-role routing, group notification, staff replies, and ticket API polling.

Run a health check:

```bash
reins wecom doctor
```

Restart or reinstall the service

```bash
reins wecom ticket-api service stop
reins wecom ticket-api service start
reins wecom ticket-api service status
```

Create a work order:

```bash
reins wecom work-order add \
  --external-id T-1001 \
  --title "楼道照明损坏" \
  --description "居民反馈 3 号楼 2 单元楼道灯不亮" \
  --location "3号楼2单元" \
  --category "物业维修" \
  --priority normal \
  --notify \
  --json
```

Notify or update an existing work order:

```bash
reins wecom work-order notify --external-id T-1001 --dry-run --json
reins wecom work-order reply --external-id T-1001 --message "已安排维修，今晚完成" --responder "物业" --json
```

Inspect records and export the Excel ledger:

```bash
reins wecom records list --limit 20 --json
reins wecom records report --json
reins wecom records export --json
```

Poll the internal ticket API:

```bash
reins wecom ticket-api doctor --json
reins wecom ticket-api inspect --limit 5 --json
reins wecom ticket-api poll --dry-run --json
reins wecom ticket-api poll --watch --json-lines
reins wecom ticket-api cursor --now --json
reins wecom ticket-api cursor --reset --json
```

Install the WeCom Hermes plugin:

```bash
reins wecom install-plugin
reins plugins enable reins-wecom
```

Common WeCom environment values go in `<REINS_HOME>/.env`:

```dotenv
REINS_WECOM_NOTIFY_GROUP_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
REINS_WECOM_NOTIFY_USERS_PROPERTY=user_a,user_b
REINS_WECOM_NOTIFY_USERS_CLEANING=user_c
REINS_WECOM_NOTIFY_USERS_POLICE=user_d
REINS_WECOM_NOTIFY_USERS_HOSPITAL=user_e
REINS_WECOM_NOTIFY_USERS_COMMUNITY=user_f
REINS_WECOM_NOTIFY_USERS_DEFAULT=user_admin
REINS_WECOM_REPLY_BOT_NAME=社区美女

REINS_TICKET_API_URL=https://example.com/internal/tickets
REINS_TICKET_API_TOKEN=replace-me
REINS_TICKET_API_STATUSES=pending_dispatch,dispatched,reopened,notification_failed
REINS_TICKET_API_POLL_INTERVAL=30
REINS_TICKET_API_LIMIT=20

REINS_WECOM_EXPORT_DIR=/absolute/path/for/staff-documents
```

`reins wecom ticket-api service ...` manages a macOS `launchd` poller only. On Windows, run `reins wecom ticket-api poll --watch --json-lines` in a terminal or wire that command into your own scheduled task/service wrapper.

## Artifacts And Presentations

Artifacts can create local DOCX/XLSX/PPTX/TXT/JSON files from chat-style requests:

```bash
reins artifacts --help
reins chat "create a maintenance notice document for residents"
```

Presentation jobs:

```bash
reins presentation --help
reins presentation doctor
```

Optional presentation engines live under `external/`; configure and verify them with the presentation doctor before relying on them in development.

## Migration

Copy existing Hermes data into the Reins home:

```bash
reins migrate hermes
```

Source defaults:

```text
macOS/Linux: ~/.hermes
Windows:     %LOCALAPPDATA%\hermes
```

The migration copies missing files only and writes:

```text
<REINS_HOME>/.migrated-from-hermes
```

## Developer Checks

Useful checks before handing off changes:

```bash
.venv/bin/python -m compileall -q src/reins
.venv/bin/python -m unittest tests.test_windows_compat
reins finance doctor
reins wecom doctor

cd web
npm test
npm run build
```

On Windows, replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`.

## Development Notes

- Keep product code in `src/reins/` and `web/`.
- Keep `vendor/hermes-agent/` aligned with upstream Hermes instead of patching it casually.
- Store Reins-specific runtime files under `REINS_HOME`.
- Keep feature storage local-first and usable without network access when possible.
- Use platform-aware paths and subprocess commands; avoid hardcoded `.venv/bin`, `/tmp`, `open`, or shell-only npm scripts.
