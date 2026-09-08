# Architecture

## Runtime and entry points

MDC is a Python application using FastAPI and Uvicorn. `app.py` is both the application entry point and the primary application module. Its FastAPI lifespan initializes the local database and persistent folders; it serves `static/index.html` at `/` and mounts `static/` at `/static`.

The supported launch wrappers are `run_windows.bat` and `run_mac_linux.sh`. Both create `.venv` if needed, install `requirements.txt`, and launch `uvicorn app:app`. The Windows wrapper selects a free local port from 8000–8010; the macOS/Linux script uses 8000.

## Frontend

The frontend is a server-served, no-build static application:

- `static/index.html` provides the UI shell.
- `static/js/app.js` owns API calls, browser/session state, panels, workflow UI, and campus interactions.
- `static/js/camera.js`, `world-config.js`, and `world-assets.js` support the campus map.
- `static/css/app.css` and `world.css` provide application and map styling.
- `static/assets/` contains the canonical building, agent, environment, and UI art assets, plus `asset-manifest.json` feature metadata.

Browser state includes an Ask the Campus history stored for the browser session. API state is fetched from the server and WebSocket broadcasts notify connected clients after changes.

## Backend and API organization

`app.py` contains request models, schema initialization/migrations, state assembly, workflows, and all HTTP/WebSocket routes. Principal API groups are:

- campus state and Ask the Campus: `/api/state`, `/api/campus/ask`;
- people, work sessions, and reports: `/api/people`, `/api/work-sessions`, `/api/poe/command`, `/api/work-report`;
- projects, tasks, approvals, and Chief workflows: `/api/chief/plan`, `/api/projects/*`, `/api/tasks/*`, `/api/approvals/*`;
- Library intake, catalog, index, collections, playbooks, memory, and repository files: `/api/library/*`, `/api/playbooks*`, `/api/memory*`, `/api/repository/*`;
- environment, weather, seasons, human-reviewed phenology, events, and Stella Daily Steward: `/api/environment/*`, `/api/events*`, `/api/stella/daily`;
- grants and AI controls: `/api/grants*`, `/api/vernadette/command`, `/api/ai/*`.

The application keeps a module-global WebSocket hub and one module-global `workflow_task`; approved plans and demo workflows are launched with `asyncio.create_task`.

## Storage and persistent data

SQLite is the system of record at `mavis.db` beside `app.py` (or a temporary alternate `DB_PATH` during tests). `init_db()` creates and incrementally migrates the schema. Main entities include buildings, agents, people, work sessions/audit, grants, events, projects, tasks, approvals, notes/activity logs, AI controls/calls, workflow artifacts, Library metadata/indexes/inbox, weather/seasonal data, playbooks, and institutional memory.

Durable files live beside the active database:

- `repository/` — project repository files and scanned metadata;
- `library/inbox/` — submitted material awaiting cataloging;
- `library/catalog/` — trusted Library source files.

No `mavis.db` was present in the audited checkout; `library/` and `repository/` directories were present.

## Role and service modules

- `agents/` implements Chief planning/review/revision, Research, Programs, and deterministic trusted-Library search.
- `ai/` reads `.env` plus process environment and routes Chief, Research, Programs, and Caretaker requests to configured OpenAI or Gemini providers.
- `library_indexer.py` extracts text locally from supported PDF, DOCX, PPTX, and XLSX inputs.
- `weather_provider.py` reads an optional Weather Underground key, uses a personal weather station when available, and falls back to Open-Meteo forecasts.
- `grant_provider.py` searches the public Grants.gov Search2 API; it does not submit applications.
- `upgrade_helper.py` powers the provided import/backup/restore scripts.

## Important data flows

1. A user request can become a Chief plan, then an explicit human approval. Approved plans run role workflows, save artifacts, enter final review, and may be archived only after the relevant human gate.
2. Library files move from inbox to human cataloging before they become trusted Library materials. Local text extraction feeds the SQLite search index; the Librarian searches this trusted local index.
3. Weather refresh optionally queries Weather Underground for the configured station and queries Open-Meteo for forecast data. Results are stored in SQLite and read by the environment UI and Daily Steward.
4. Phenology observations are stored locally with source and review status. System suggestions remain suggestions until a human confirms or rejects them; they do not feed planning in Phase 1.
5. Ask the Campus routes some requests to deterministic local handlers; configured AI role calls are recorded in `ai_calls` and guarded by the AI controls.

## Configuration

Environment names documented in `.env.example`: `GEMINI_API_KEY`, `GEMINI_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `CHIEF_PROVIDER`, `RESEARCH_PROVIDER`, `PROGRAMS_PROVIDER`, `CARETAKER_PROVIDER`, and `WEATHER_UNDERGROUND_API_KEY`. The weather adapter also recognizes the legacy names `WUNDERGROUND_API_KEY` and `WEATHER_COM_API_KEY` in its merged environment. Never place values in documentation or source control.
