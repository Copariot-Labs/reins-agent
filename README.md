# Reins Agent

Reins Agent is a local-first personal agent product built on top of the upstream Hermes Agent runtime. Reins owns the product wrapper, local data home, finance tools, reports, Web UI integration, and user-facing commands. Hermes Agent remains the upstream core for the agent loop, chat runtime, models, skills, gateway, memory, and related platform features.

The `vendor/hermes-agent/` directory is treated as upstream source. Do not modify it for Reins product work; update it from the Hermes Agent repository when needed.

## Features

- `reins` CLI wrapper with Reins-owned commands and Hermes pass-through commands.
- Isolated Reins data directory under `~/.reins` by default.
- Optional migration from an existing `~/.hermes` directory.
- Local finance module with natural-language transaction parsing, SQLite storage, reports, CSV export, and Hermes-compatible plugin tools.
- Web dashboard in `web/`, including a Finance section for summaries, recent transactions, tables, and CSV export.

## Repository Layout

```text
.
├── src/reins/                  # Reins Python package and CLI wrapper
│   ├── compat/                 # Hermes compatibility layer and Reins-owned commands
│   └── features/finance/       # Finance parser, repository, reports, tools, exports
├── web/                        # Vue/Koa Hermes Web UI with Reins finance dashboard
├── scripts/                    # Local helper scripts
├── vendor/hermes-agent/        # Upstream Hermes Agent runtime, do not edit here
└── pyproject.toml              # Reins package metadata
```

## Requirements

- Python 3.11+
- Node.js 23+ for the Web UI
- npm
- Git submodules initialized for `vendor/hermes-agent/`

## Setup

```bash
# Clone the Reins repository
git clone https://github.com/Copariot-Labs/reins-agent.git
cd reins-agent

# Initialize Hermes upstream submodule
git submodule update --init --recursive

uv venv
source .venv/bin/activate

uv pip install -e vendor/hermes-agent
uv pip install -e .

cd web
npm install
cd ..
```

Check the install:

```bash
reins version
reins about
reins debug-env
```

## Data Directories

Reins defaults to:

```text
~/.reins
```

Important paths:

```text
~/.reins/finance/finance.sqlite       # Finance SQLite database
~/.reins/finance/export/              # Finance CSV exports
~/.reins/web-ui/                      # Web UI runtime state when launched by Reins
~/.reins/plugins/reins-finance/       # Installed finance plugin
```

## CLI Usage

Show help:

```bash
reins --help
```

Reins-owned commands:

```bash
reins version
reins about
reins migrate hermes
reins update
reins finance --help
reins web
reins debug-env
```

Hermes pass-through commands still work through `reins`, for example:

```bash
reins chat
reins doctor
reins model
reins tools
reins config
reins gateway
reins sessions
```

Direct chat prompts are normalized for the Hermes CLI:

```bash
reins chat "hello"
```

Finance-looking direct chat messages may be handled by the Reins finance preprocessor:

```bash
reins chat "今天买咖啡 28"
```

## Finance

Run a database health check:

```bash
reins finance doctor
```

Parse a transaction without recording it:

```bash
reins finance parse "今天买咖啡 28"
```

Record expenses and income:

```bash
reins finance add "今天买咖啡 28"
reins finance add "昨天打车 45"
reins finance add "收到客户转账 3000"
```

List and report:

```bash
reins finance list
reins finance list --month 2026-06
reins finance report
reins finance report --month 2026-06
```

Void a transaction:

```bash
reins finance void 1
```

Export CSV:

```bash
reins finance export csv
reins finance export csv --month 2026-06
reins finance export csv --output ~/Desktop/reins-finance.csv
reins finance export csv --include-voided
```

Install the finance plugin into the Reins plugin directory:

```bash
reins finance install-plugin
reins plugins enable reins-finance
```

The installed plugin exposes finance parsing, recording, listing, and summary tools to the Hermes runtime.

## Web UI

Start the Web UI through Reins:

```bash
reins web
```

This launches the `web/` app with Reins-specific environment values:

```text
REINS_HOME
HERMES_HOME
HERMES_BIN
HERMES_WEB_UI_HOME
HERMES_AGENT_ROOT
HERMES_AGENT_BRIDGE_PYTHON
```

The development Web UI runs the backend and frontend together. By default, the client is served on port `8649` and the backend on port `8647`.

You can also use the helper script:

```bash
scripts/start-reins-web.sh
```

For direct web development:

```bash
cd web
npm run dev
npm run build
npm test
```

The Web UI includes a Finance dashboard at:

```text
/hermes/finance
```

It reads from the Reins finance database, displays monthly totals and transactions, and exports CSV data through the dashboard.

## Migrating From Hermes

To copy existing Hermes data from `~/.hermes` into `~/.reins`:

```bash
reins migrate hermes
```

The migration copies files that do not already exist and writes a marker file:

```text
~/.reins/.migrated-from-hermes
```

The original `~/.hermes` directory is not deleted. To rerun migration:

```bash
reins migrate hermes --force
```

## Development Notes

- Keep Reins product code in `src/reins/` and `web/`.
- Keep `vendor/hermes-agent/` aligned with the upstream Hermes Agent repository.
- Prefer adding Reins-specific behavior in the compatibility layer instead of patching upstream Hermes code.
- Finance storage is local SQLite and should remain usable without network access.
- The Web UI package has its own README and development docs under `web/`.

## Verification

Useful local checks:

```bash
reins finance doctor
reins finance add "今天买咖啡 28"
reins finance report

cd web
npm run build
```
