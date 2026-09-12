# Development Status

Audit scope: repository contents as inspected on 2026-09-07. This document does not treat README release history as proof beyond what is present in code and tests.

## Working / Implemented

- FastAPI/SQLite campus application with static campus-map UI, canonical assets, WebSocket refreshes, and seeded buildings/agents.
- Projects, tasks, approvals, revision workflows, role artifacts, notes, activity log, and AI control/cost records.
- Stella Daily Steward and Ask the Campus routing, including deterministic local paths and optional role AI advice.
- Daily Steward's Library Class Commitment Spine uses scheduled, explicitly project-linked events in a 14-day look-ahead to support that active project's existing next task. The bounded date boost is 18 points at 0–3 days, 12 at 4–7 days, and 6 at 8–14 days; it remains below human-gate and blocker precedence, creates no work, and does not assume that a task is preparation.
- Trusted Library intake, human cataloging, local text extraction/indexing, collections, playbooks, and institutional-memory records.
- People ledger, work sessions with audit records, clock in/out, deterministic Poe commands, reports, and CSV export.
- Events/calendar foundation, local moon calculation, weather/seasonal data storage and refresh adapter.
- Phase 1 phenology observations with human, imported, and suggested sources; Rose review can confirm or reject suggestions without feeding planning logic.
- Phase 2 trusted phenology history comparison across years, including optional location filtering and factual date summaries.
- Phase 5 Seasonal Context: Rose's read-only, 45-day seasonal evidence bridge separates established observations from open checks; Stella can summarize it through Ask Campus and users can inspect the same context in Weather & Seasons → Phenology, without affecting Daily Steward or planning.
- Grants.gov discovery/import and local grant tracking.
- 201 test functions in `tests/test_smoke.py`, covering backend behavior plus static/UI regression guards.

## Partial

- All backend orchestration, schema, and route logic reside in the 465 KB `app.py`; there is no separated controller/service/repository layer for most feature areas.
- The frontend is operational but most UI state and rendering are concentrated in the 221 KB `static/js/app.js`.
- Canonical art is present for several buildings and staff; the asset tree has no dedicated Vernadette or Poe sprite directories, while code uses stable IDs and UI representations for both.
- The test suite is in a dedicated `requirements-dev.txt`, which includes `requirements.txt` plus pinned `pytest` and Pillow. The application launch scripts intentionally install runtime requirements only.

## Referenced / Planned

- Google Calendar synchronization is explicitly shown as disconnected/deferred in code/tests and README history.
- The product canon includes Plant/Living System and Property Asset concepts; no corresponding standalone SQLite tables were found.
- The next operating-cycle milestone is durable community contribution tracking for donations, goods, services, equipment/space, introductions/outreach, outstanding offers, thank-yous, and follow-ups. It is not implemented in the Commitment Spine.
- Personal/nonprofit permissions require a separate design before shared access is expanded.
- The README identifies future integrations such as broader grant sources and additional operational automation; they were not treated as implemented.

## Technical Risks

1. `app.py` combines schema migration, persistence, HTTP APIs, workflow orchestration, and domain logic; unrelated edits can affect broad behavior.
2. `static/js/app.js` and the CSS/UI shell are tightly coupled to exact DOM IDs, asset paths, cache keys, and map coordinates. Tests intentionally guard many literal strings.
3. SQLite migrations are inline and additive on startup. Schema edits require both upgrade-path and clean-database verification.
4. A module-global `workflow_task` permits one workflow at a time and is process-local; its lifecycle affects approvals, demos, resumes, and UI state.
5. File paths are derived from `DB_PATH.parent`; database relocation changes the repository and Library roots as well.

## Test Coverage Gaps

- The suite is one large smoke/regression file rather than feature-scoped tests, making failure diagnosis and selective execution harder.
- Browser behavior is protected mainly by source-string assertions; no browser-driven end-to-end test infrastructure was found.
- The external Weather Underground, Open-Meteo, Grants.gov, OpenAI, and Gemini integrations have mocked/unit coverage but no documented live integration test process.
- This audit environment had no discoverable Python executable or `.venv`, so the existing suite and server could not be executed here.
