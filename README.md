# Reins Agent

Reins Agent is a local-first personal agent product. Reins owns the product wrapper, local data home, Finance tools, WeCom work-order tools, Office documents, and Web UI integration. The bundled agent runtime provides chat, models, memory, skills, gateways, and the agent loop.

`vendor/hermes-agent/` is upstream source. Do not patch it for Reins product work unless you are intentionally updating the vendored runtime.

## Repository

```text
.
├── src/reins/                  # Reins Python package and CLI
│   ├── compat/                 # Hermes compatibility, bootstrap, env, web launcher
│   └── features/               # Reins-owned product features
│       ├── finance/            # Local finance parser, SQLite, reports, CSV, plugin
│       ├── wecom/              # WeCom work orders, ticket API polling, Excel ledger
│       └── office/             # Chat-triggered Word, Excel, and PowerPoint creation
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
- Git

## Setup

macOS/Linux:

```bash
git clone https://github.com/Copariot-Labs/reins-agent.git
cd reins-agent

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
<REINS_HOME>/office/
<REINS_HOME>/web-ui/
<REINS_HOME>/plugins/
<REINS_HOME>/.env
```

`reins` sets `HERMES_HOME` to `REINS_HOME` so Hermes data stays inside the Reins product home. `REINS_HOME` and `HERMES_HOME` both support absolute paths, `~`, `$VAR`, `${VAR}`, and Windows `%VAR%` expansion.

Reins also creates one user-owned workspace that can be opened with Finder or Windows File Explorer:

```text
macOS/Linux: ~/Documents/Reins Workspace
Windows:     %USERPROFILE%\Documents\Reins Workspace

Inbox/
Word/
Excel/
PowerPoint/
Generated/
Projects/
```

Office files, chat uploads, agent-created files, and exports use this workspace. Users can add or edit files there directly, and Reins reads the current filesystem on the next request. Set `REINS_WORKSPACE_ROOT` to override the default location. Office indexes, previews, backups, databases, and application state remain under `REINS_HOME`.

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
reins office --help
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

## Ubuntu Desktop Deployment

Use the Ubuntu installer for a normal-user desktop deployment. It discovers the
repository, Python, Node.js, Reins data, workspace, and localized desktop paths
at runtime; builds the production Web UI; installs a `systemd --user` Web
service; installs and enables the WeCom plugin and supported poller; and creates
a desktop launcher.

Prerequisites:

- Run the installer while logged into the Ubuntu desktop as the target user.
- Do not run it with `sudo`.
- Install Python 3.11+, `uv`, Node.js 23+, npm, `curl`, and `xdg-utils`.
- Configure `<REINS_HOME>/.env` before installing the WeCom poller.

Install:

```bash
chmod +x deploy/linux/install.sh
deploy/linux/install.sh
```

The installer is idempotent. It binds the production Web UI to
`127.0.0.1:8648`, enables user lingering for startup at system boot, and uses
the Web UI as the gateway lifecycle owner. Custom paths and installation
choices are remembered under `~/.config/reins/`.

After installation, a super administrator can click **Update Reins** in the Web
UI sidebar. The updater downloads the current Git branch with a fast-forward
pull, rebuilds the application, restarts the Web UI and WeCom poller, and
reloads the browser. No terminal is required.

Existing Ubuntu installations created before the update button was added need
one final manual update to install the updater service:

```bash
git pull --ff-only
deploy/linux/install.sh
```

Useful options:

```bash
deploy/linux/install.sh --skip-build
deploy/linux/install.sh --skip-wecom
deploy/linux/install.sh --no-linger
deploy/linux/install.sh --no-desktop
deploy/linux/install.sh --reins-home /absolute/data/path
deploy/linux/install.sh --workspace /absolute/workspace/path
```

Check the installation:

```bash
systemctl --user status reins-web.service
curl -fsS http://127.0.0.1:8648/health
reins wecom ticket-api service status
journalctl --user -u reins-web.service -f
journalctl --user -u reins-update.service -f
tail -f ~/.reins/logs/update.log
```

Uninstall services and launchers while preserving application code and data:

```bash
deploy/linux/uninstall.sh
```

## Windows Desktop Deployment

Prerequisites:

- Windows 10/11 with PowerShell 5.1 or newer.
- Git, Python 3.11+, `uv`, Node.js 23+, and npm available in `PATH`.
- Run every command as the target desktop user, not as Administrator.

Clone and prepare the configuration:

```powershell
git clone https://github.com/Copariot-Labs/reins-agent.git
cd reins-agent

New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\reins"
notepad "$env:LOCALAPPDATA\reins\.env"
```

Add the required model/provider and WeCom values to the UTF-8 `.env` file, then
install:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows\install.ps1
```

The installer is idempotent. After installation, a super administrator can
click **Update Reins** in the Web UI sidebar. The on-demand `Reins Updater`
Scheduled Task stops the running tasks, performs a fast-forward Git pull,
rebuilds the application, restarts Reins, and reloads the browser. This avoids
locking `.venv\Scripts\reins.exe` while Python packages are updated.

Existing Windows installations created before the update button was added need
one final manual update to register the updater task:

```powershell
git pull --ff-only
.\deploy\windows\install.ps1
```

Useful options:

```powershell
.\deploy\windows\install.ps1 -SkipBuild
.\deploy\windows\install.ps1 -SkipWeCom
.\deploy\windows\install.ps1 -NoDesktop
.\deploy\windows\install.ps1 -ReinsHome "D:\ReinsData"
.\deploy\windows\install.ps1 -Workspace "$env:USERPROFILE\Documents\Reins"
```

Use `-SkipBuild` only when the Windows `.venv` and `web\dist` already match the
current code. Custom data and workspace paths are remembered under
`%LOCALAPPDATA%\reins-deploy`. Activating `.venv` in a terminal for CLI work is
safe and does not affect the already installed tasks:

```powershell
.\.venv\Scripts\Activate.ps1
reins model
reins --help
```

Check or restart the installed application:

```powershell
Get-ScheduledTask -TaskName "Reins Web UI"
Get-ScheduledTask -TaskName "Reins Updater"
Start-ScheduledTask -TaskName "Reins Web UI"
Invoke-WebRequest http://127.0.0.1:8648/health -UseBasicParsing
reins wecom ticket-api service status
```

Logs are in `%LOCALAPPDATA%\reins\logs` by default. Update progress is written
to `update.log`; a failed update also shows a Windows dialog and restarts the
previous services when possible. Uninstall startup tasks and shortcuts while
preserving the repository and all Reins data:

```powershell
.\deploy\windows\uninstall.ps1
```

For PCs in China, configure an accessible Git remote plus npm, uv/Python, and
Node.js mirrors before installation. The one-click updater uses the checkout's
existing Git remote and the machine's existing package-manager configuration.
Runtime traffic remains local except for the model provider, ticket API, and
WeCom endpoints configured in `.env`.

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

After configuring the ticket API and WeCom values in `.env`, install the
background poller:

```bash
reins wecom ticket-api service install
reins wecom ticket-api service status
reins wecom ticket-api service stop
reins wecom ticket-api service start
reins wecom ticket-api service uninstall
```

The same commands manage:

- macOS: a user `launchd` agent.
- Windows: the `Reins WeCom Ticket Poller` Task Scheduler task.
- Ubuntu/Linux: the `reins-wecom-ticket-poller.service` systemd user unit.

Installation starts the poller immediately and enables it for future user
sessions. Ubuntu logs are stored under `<REINS_HOME>/logs/`. On a headless
Ubuntu server that must continue after logout, an administrator may also enable
systemd user lingering for the Reins account:

```bash
sudo loginctl enable-linger <reins-user>
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
REINS_WECOM_NOTIFY_USERS_HUMAN_REVIEW=user_admin
REINS_WECOM_NOTIFY_USERS_DEFAULT=user_admin
REINS_WECOM_REPLY_BOT_NAME=社区美女

# Hybrid routing: rules for known categories, Hermes for ambiguous tickets.
REINS_WECOM_ROUTING_MODE=hybrid
REINS_WECOM_ROUTING_CONFIDENCE=0.85
REINS_WECOM_ROUTING_TIMEOUT=15

REINS_TICKET_API_URL=https://example.com/internal/tickets
REINS_TICKET_API_TOKEN=replace-me
REINS_TICKET_API_STATUSES=pending_dispatch,dispatched,reopened,notification_failed
REINS_TICKET_API_POLL_INTERVAL=30
REINS_TICKET_API_LIMIT=20

REINS_WECOM_EXPORT_DIR=/absolute/path/for/staff-documents
```

The notification webhook must belong to the shared WeCom group. Recipient
values must be internal WeCom UserIDs so the group robot can create real
mentions.

Windows `.env` path example:

```dotenv
REINS_WECOM_EXPORT_DIR=%USERPROFILE%\Documents\Reins
```

WeCom timestamps are rendered in `Asia/Shanghai` (UTC+8). The Windows poller
forces UTF-8 for Chinese ticket content and logs. Keep `<REINS_HOME>/.env`
encoded as UTF-8.

SQLite is the authoritative work-order store. On Windows, staff may keep the
Excel ledger open: ticket recording and WeCom notification continue, and the
command reports that the workbook refresh is pending. Close Excel and run
`reins wecom records export` to refresh it.

## Office

Reins Office creates local DOCX/XLSX/PPTX files from the Office page or chat-style requests:

```bash
reins office --help
reins chat "create a maintenance notice document for residents"
```

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
