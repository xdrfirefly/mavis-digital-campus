# Development Status

Audit scope: repository contents as inspected on 2026-09-07. This document does not treat README release history as proof beyond what is present in code and tests.

## Working / Implemented

- v0.10 Phase 1 Portfolio-State Normalization keeps workflow `projects.status` unchanged while adding human-governed Active Now, Dormant, Nursery / Future Idea, Completed, and Dead / Retired portfolio states; project purpose, canonical six-staff ownership, why-it-matters, state rationale, next review date, and auditable state history; and bounded task blocker/optional metadata.
- v0.10 legacy migration maps only workflow `Completed` to portfolio Completed and known in-progress workflow states to provisional Active Now. Ambiguous rows remain visibly unclassified for trusted-operator review. Nursery/Dormant/completed/unclassified activation and retirement require explicit confirmation and a human reason; Dead / Retired is terminal, and no AI or background path can activate projects.
- Ordinary Daily Steward task, blocker, linked-commitment, project-linked grant, and project-scoped memory candidates now require portfolio Active Now. The Daily Steward response shape itself is unchanged pending the separately scoped v0.10 dispatcher phase.
- FastAPI/SQLite campus application with static campus-map UI, canonical assets, WebSocket refreshes, and seeded buildings/agents.
- Projects, tasks, approvals, revision workflows, role artifacts, notes, activity log, and AI control/cost records.
- Ask Campus deterministically answers narrowly matched personal calendar questions for today, tomorrow, the next seven days, and named weekdays. Future focus uses the existing target-date-aware Daily Steward, makes no writes or AI calls, and calendar event content is excluded from external AI prompts.
- Stella Daily Steward and Ask the Campus routing, including deterministic local paths and optional role AI advice.
- Daily Steward's Library Class Commitment Spine uses scheduled, explicitly project-linked events in a 14-day look-ahead to support that active project's existing next task. The bounded date boost is 18 points at 0–3 days, 12 at 4–7 days, and 6 at 8–14 days; it remains below human-gate and blocker precedence, creates no work, and does not assume that a task is preparation.
- Trusted Library intake, human cataloging, local text extraction/indexing, collections, playbooks, and institutional-memory records.
- v0.9.9 Phase 1 preparation moves Library upload staging, filename normalization, hashing, deduplication, and inbox registration into framework-neutral `library_intake.py` without changing the browser upload or human cataloging workflow. Office archive extraction now fails closed on excessive entry counts, individual or cumulative expansion, encrypted entries, and suspicious compression ratios.
- Rose can answer explicit Library inventory requests in Ask Campus through deterministic local retrieval, listing exact stored titles and material types only for `Cataloged` materials in `Active` collections. Confirmed empty results and retrieval failures remain distinct; the inventory path performs no AI/network calls or writes and does not replace topic search.
- People ledger, work sessions with audit records, clock in/out, deterministic Poe commands, reports, and CSV export.
- People now opens to a simplified Directory with separate Work Hours and Contributions subviews. Person profiles expose a timezone-aware Monthly Participation Record derived from completed Work Sessions, a clearly labeled 80-hour monthly tracking target, streamlined audited manual Add Hours, exact person/month CSV, and a print-friendly browser record with verifier lines and an eligibility disclaimer. Organizations have no personal participation target.
- Manual Community Contribution Ledger for Person/Organization identities, offers, received money/sponsorships, goods/materials, professional services, equipment/space, and introductions/outreach. It supports project/event links, existing follow-up tasks, completed work-session links, thank-you/follow-up status, multiple fulfillments, unknown values, and idempotent received-entry submission keys without adding ledger details to shared state, WebSockets, exports, AI context, or general logs.
- Events/calendar foundation, local moon calculation, weather/seasonal data storage and refresh adapter.
- Manual read-only Google Calendar v1 for the primary calendar, using the existing event model and a bounded local cache; no startup/state refresh, write-back, or incremental sync.
- Google Drive v0.9.9 explicit snapshot intake with the unchanged `drive.file` scope and approved-root/account binding. File selection and containing-folder approval use a separate callback purpose that cannot replace the root. Every parent is retrieved authoritatively; direct-root files need explicit file approval, while nested files repeat explicit folder approval until the full chain reaches the root. Human-confirmed, bounded downloads/exports create SHA-deduplicated `google_drive` rows only in quarantined Incoming Materials with provenance. There is no Drive browser, crawl, synchronization, write-back, automatic import, trusted promotion, pre-approval indexing, shared-state/WebSocket content, or AI access.
- v0.9.9 Phase 2/3 adds independently account/root-bound metadata, bounded parent ancestry, one-level listings, ordinary-file streaming, deterministic Docs/Sheets/Slides/Drawings exports, and explicit import review. Live verification on 2026-09-30 confirmed that approving only a root does not reveal children; selecting a nested file reveals its authoritative parent ID but not the parent metadata; explicitly approving the containing folder exposes the chain and persists access for the existing account/client grant.
- Phase 1 phenology observations with human, imported, and suggested sources; Rose review can confirm or reject suggestions without feeding planning logic.
- Phase 2 trusted phenology history comparison across years, including optional location filtering and factual date summaries.
- Phase 5 Seasonal Context: Rose's read-only, 45-day seasonal evidence bridge separates established observations from open checks; Stella can summarize it through Ask Campus and users can inspect the same context in Weather & Seasons → Phenology, without affecting Daily Steward or planning.
- Grants.gov discovery/import and local grant tracking.
- The smoke/regression suite in `tests/test_smoke.py` covers backend behavior plus static/UI regression guards.

## Partial

- All backend orchestration, schema, and route logic reside in the 465 KB `app.py`; there is no separated controller/service/repository layer for most feature areas.
- The frontend is operational but most UI state and rendering are concentrated in the 221 KB `static/js/app.js`.
- Canonical art is present for several buildings and staff; the asset tree has no dedicated Vernadette or Poe sprite directories, while code uses stable IDs and UI representations for both.
- The test suite is in a dedicated `requirements-dev.txt`, which includes `requirements.txt` plus pinned `pytest` and Pillow. The application launch scripts intentionally install runtime requirements only.

## Referenced / Planned

- Broader Google Calendar support (multiple calendars, write-back, incremental sync, and automatic refresh) remains deferred.
- The product canon includes Plant/Living System and Property Asset concepts; no corresponding standalone SQLite tables were found.
- Natural-language contribution capture, automated communications, contribution exports/dashboards, and broad reporting remain deferred.
- The supported deployment is local trusted-operator use on `127.0.0.1`. There is no authentication or authorization; personal/nonprofit permissions require a separate design before shared, volunteer-facing, LAN, or public access is expanded.
- The README identifies future integrations such as broader grant sources and additional operational automation; they were not treated as implemented.

## Technical Risks

1. `app.py` combines schema migration, persistence, HTTP APIs, workflow orchestration, and domain logic; unrelated edits can affect broad behavior.
2. `static/js/app.js` and the CSS/UI shell are tightly coupled to exact DOM IDs, asset paths, cache keys, and map coordinates. Tests intentionally guard many literal strings.
3. SQLite migrations are inline and additive on startup. Schema edits require both upgrade-path and clean-database verification.
   v0.10 deliberately leaves ambiguous legacy portfolio states as `NULL` until human review, so operators upgrading a database with nonstandard workflow statuses must classify those projects before they can enter ordinary operational focus.
4. A module-global `workflow_task` permits one workflow at a time and is process-local; its lifecycle affects approvals, demos, resumes, and UI state.
5. File paths are derived from `DB_PATH.parent`; database relocation changes the repository and Library roots as well.

## Test Coverage Gaps

- The suite is one large smoke/regression file rather than feature-scoped tests, making failure diagnosis and selective execution harder.
- Browser behavior is protected mainly by source-string assertions; no browser-driven end-to-end test infrastructure was found.
- The external Weather Underground, Open-Meteo, Grants.gov, OpenAI, and Gemini integrations have mocked/unit coverage but no documented live integration test process.
- This audit environment had no discoverable Python executable or `.venv`, so the existing suite and server could not be executed here.
