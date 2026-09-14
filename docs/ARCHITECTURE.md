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
- local trusted-operator community contributions: on-demand `/api/community-contributions*` routes, intentionally excluded from `/api/state`, WebSocket payloads, exports, and AI context;
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
- `google_calendar_provider.py` performs manual, read-only OAuth and bounded primary-calendar reads. It returns only Google-owned schedule fields and keeps access tokens in memory.
- `upgrade_helper.py` powers the provided import/backup/restore scripts.

## Important data flows

1. A user request can become a Chief plan, then an explicit human approval. Approved plans run role workflows, save artifacts, enter final review, and may be archived only after the relevant human gate.
2. Library files move from inbox to human cataloging before they become trusted Library materials. Local text extraction feeds the SQLite search index; the Librarian searches this trusted local index.
3. Weather refresh optionally queries Weather Underground for the configured station and queries Open-Meteo for forecast data. Results are stored in SQLite and read by the environment UI and Daily Steward.
4. Phenology observations are stored locally with source and review status. Rose can compare trusted observed/confirmed records by normalized subject and stage across years; suggestions remain excluded until human review and phenology does not feed planning.
5. Ask the Campus routes some requests to deterministic local handlers; configured AI role calls are recorded in `ai_calls` and guarded by the AI controls. A narrowly matched Rose inventory request reads only titles and recorded material types for `Cataloged` materials in `Active` Library collections. A successful zero-row query is reported as no Cataloged materials in Active collections, while retrieval errors are reported separately; this path makes no AI/network calls or writes and does not receive contribution data.
6. Daily Steward reads scheduled events explicitly linked to active projects within a 14-day look-ahead. It adds a bounded boost to that project's already-recorded next task (18 points at 0–3 days, 12 at 4–7, and 6 at 8–14), labels the task only as supporting the named dated commitment, and performs no writes. Unlinked, inactive, cancelled, completed, past, and more-distant events do not influence task priority; approvals, blockers, calendar workload limits, weather adjustments, and the three-item maximum remain authoritative.
7. Monthly Participation Records are read-time projections over completed `work_sessions` for one Person and one calendar month in the configured Campus timezone. Date-only `manual_duration` sessions use `work_date`; normal sessions use the localized start date; open sessions are excluded. The 80-hour value is a display/reporting target for Person identities only, not an eligibility determination. Manual Add Hours uses the existing `work_sessions` table and audit trail rather than creating another hours ledger. Person/month CSV and browser printing use the same projection.
8. Ask Campus handles narrowly matched personal schedule questions with an explicit today, tomorrow, next-seven-days, or named-weekday target before every AI-backed agent branch. Listing answers reuse `calendar_summary`; focus answers reuse Daily Steward with the resolved target date. Calendar event content is excluded from all external AI prompts. The optional Daily Steward target date preserves current-day behavior when omitted and does not project a currently open work session into a future day.

9. Google Calendar v1 manually expands primary-calendar occurrences for a 30-day-past/180-day-future window and upserts them into `events`. Google owns schedule fields; Campus project/type/commitment/notes annotations survive refresh. State reads never call Google, disconnect retains cached events, and no attendee, organizer, description, conferencing, attachment, reminder, or response data crosses the provider boundary.

The next contribution layer is intentionally deferred: natural-language capture, exports/dashboards, broader reporting, and any automated communications. Personal/nonprofit visibility and permissions require a separate design before shared access is expanded.

## Local access boundary

The application has no authentication or authorization layer. Supported launchers bind Uvicorn to `127.0.0.1`, so the current deployment boundary is one trusted operator on the local machine. Community Contribution Ledger endpoints are on-demand but are not private from other software or users able to access that local server. Do not expose MDC on a LAN, public host, shared reverse proxy, or volunteer-facing device without first adding authenticated users, endpoint authorization, and field-level visibility rules.

Community contribution records use the existing identity, project, event, task, and work-session records. Offers and received contributions are separate; a received contribution may fulfill an offer or stand alone. Work sessions remain authoritative for time. Ledger mutations do not broadcast details or add them to general activity logs, and current exports and AI prompts do not read the ledger.

## Configuration

Environment names documented in `.env.example`: `GEMINI_API_KEY`, `GEMINI_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `CHIEF_PROVIDER`, `RESEARCH_PROVIDER`, `PROGRAMS_PROVIDER`, `CARETAKER_PROVIDER`, `WEATHER_UNDERGROUND_API_KEY`, `GOOGLE_CALENDAR_CLIENT_ID`, and `GOOGLE_CALENDAR_CLIENT_SECRET`. The Google refresh token is stored separately in ignored `.google-calendar-token.json`. The token and Google OAuth credential values are excluded from portable backups and previous-version imports, so Calendar must be reconnected after an upgrade. Never place values in documentation or source control.
