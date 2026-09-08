# Mavis Digital Campus

Mavis Digital Campus (MDC) is an institutional-support system for The Mavis Institute. It coordinates operations, education, land stewardship, institutional memory, volunteers, projects, and programs while keeping human authority central.

## Start here

1. Read the relevant document in [`docs/`](docs/).
2. Inspect only the modules named there for the requested change.
3. Make the smallest coherent change, then run targeted verification.

## Repository map

- `app.py` — FastAPI application, SQLite schema, API routes, workflow orchestration.
- `static/` — browser UI, campus map, CSS, and approved visual assets.
- `agents/`, `ai/`, `prompts/` — role workflows and AI-provider integration.
- `library_indexer.py`, `weather_provider.py`, `grant_provider.py` — local library extraction and external-service adapters.
- `tests/test_smoke.py` — current regression/smoke suite.
- `docs/ARCHITECTURE.md` — technical map and data flows.
- `docs/MDC_PRODUCT_CANON.md` — stable product terminology and geography.
- `docs/DEVELOPMENT_STATUS.md` — implementation inventory and risk register.

## Setup and verification

- Windows: run `run_windows.bat` from the repository root.
- macOS/Linux: run `./run_mac_linux.sh` from the repository root.
- Direct server after dependencies are installed: `python -m uvicorn app:app --host 127.0.0.1 --port 8000`.
- Tests: `python -m pytest -q` (the current suite also imports Pillow; see Development Status for the dependency gap).

## Development rules

1. Preserve existing working functionality.
2. Never remove a working feature as a shortcut for implementing another feature.
3. Prefer small, incremental changes and one major objective at a time.
4. Test affected functionality before declaring work complete.
5. Report schema migrations and new dependencies explicitly.
6. Do not expose or commit secrets.
7. Respect canonical MDC terminology and product canon.
8. Do not redesign architecture without a concrete need.
9. Existing working code is evidence; assumptions are not.
10. Do not change product-level canon without explicit user instruction.

## Definition of done

The scoped behavior works, related regression tests pass (or a blocking baseline failure is reported), documentation is updated when behavior or setup changes, and the final summary lists changed files, verification, migrations, and dependencies.
