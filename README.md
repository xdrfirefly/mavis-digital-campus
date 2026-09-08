# Mavis Digital Campus v0.9.3 — Phenology Multi-Year Comparison

## v0.9.3 focus

This is a small polish patch built directly on the working **v0.8.7.4** baseline. It changes only two user-facing behaviors: the Campus staff feel alive again while idle, and Ask the Campus keeps a clearer newest-first conversation history.

### Ambient staff movement

- Available staff now occasionally wander a short distance around their current/home area.
- Ambient movement is **visual only**: it does not change the agent's official `building_id`, create Activity Log entries, or pretend that work happened.
- Only one available person is selected occasionally, so the map stays calm rather than looking busy for its own sake.
- When real assigned work moves an agent between buildings, ambient movement stops immediately and the existing routed work movement remains authoritative.
- Staff pause briefly after wandering and then return to their normal anchor.
- Reduced-motion browser preferences disable ambient wandering.

### Ask the Campus history

- The **newest answer now appears at the top** of the Ask response area.
- The response area has a fixed maximum height and its own vertical scrollbar.
- Scroll downward to review older exchanges.
- Up to the latest **20 exchanges** are kept for the current browser session instead of only five.
- A small sticky hint appears when there is history: **Newest response first · scroll down for older exchanges**.
- New answers reset the response panel to the top so the newest answer is immediately visible.
- Clear conversation still removes the full current-session thread.

No project, People, work-hour, grant, calendar, Library, weather, or institutional-memory data model changes were made in this patch.

### Deferred integrations retained

Google Calendar is **not connected yet**. The internal Campus Calendar remains active, but **Google Calendar sync** stays deferred until the local event model and Stella workload behavior are stable.

This release searches **Grants.gov only** for Vernadette's live grant discovery. Private foundations, West Virginia-specific sources, local funders, and corporate giving remain later expansions.

The existing **Weather & Seasons** system remains unchanged: personal-weather-station data can be used when authorized, with the regional forecast fallback retained.

Target schema: **0.9.3**.

## Upgrade

1. Extract v0.9.3 into a new folder.
2. Run `IMPORT DATA FROM PREVIOUS VERSION.bat`.
3. Point it at your working **v0.8.7.4** folder.
4. Start v0.9.3 normally.
5. Leave the Campus map open for a minute or two; available staff should occasionally move gently around their home area.
6. Ask two or three questions. The newest exchange should stay at the top; scroll down inside the response panel to see older ones.

---


# Historical baseline: v0.8.6.9.5 — Talk to Poe

> Built from the working v0.8.6.9.4 Poe Work Hours Reports + CSV release. The known-good world shell, Weather & Seasons/PWS layer, Library safeguards, Programs Auto-Archive, project workflows, People ledger, work-session audit trail, and reporting remain intact. This release deliberately adds only a conversational layer on top of Poe's existing work ledger.

## v0.8.6.9.5 — Talk to Poe

Poe can now understand a controlled set of ordinary-language work-hour requests without making an AI call. The parser is deterministic on purpose: if a person or activity is not clear enough to record safely, Poe asks for clarification rather than guessing.

Examples:

- `Poe, clock me in for farm work on the Monastic Garden.`
- `Poe, clock Lisa out.`
- `Poe, add 2 hours yesterday for Sam doing maintenance.`
- `Poe, how many volunteer hours did I have in August?`
- `Poe, show me our education hours this month.`

### What this release adds

- Adds a **Talk to Poe** box in Poe's agent panel and the People & Work area.
- Adds a **primary “me” Person record** so `me / I / my` can resolve safely. Mark one People record as **This is me**; choosing another automatically replaces the prior primary record.
- Natural clock-in commands resolve the person, activity category, participation type, and an existing project/program when the match is strong enough.
- Natural clock-out commands close that person's current open session.
- Date-only remembered durations can be recorded without pretending the user supplied exact clock times. These entries are stored as `manual_duration` with a real work date and duration; the internal sort anchors are hidden from reports.
- Natural report questions reuse the existing Work Hours Report filters and can open the exact filtered report.
- Existing CSV export now labels the entry mode; date-only remembered entries leave exact Started/Ended columns blank.
- Manual-duration corrections preserve the audit trail and ask for the work date + duration rather than exposing internal placeholder timestamps.
- Poe natural commands use **zero AI calls and zero web calls**.

### Safety / data behavior

Poe never auto-creates a person from a name mentioned in a command. The person must already exist in the People Ledger. If `me` has not been configured, Poe asks you to mark a People record first. If an activity category cannot be inferred clearly, Poe asks for the category before saving. This keeps operational records useful for later grant and government reporting.

## Local Weather & Seasons

The existing local Weather & Seasons planning layer is retained unchanged.

- `KWFLATT11` remains the preconfigured primary Mavis personal weather station.
- Weather Underground / The Weather Company PWS current observations are supported when `WEATHER_UNDERGROUND_API_KEY` is present in `.env`.
- Open-Meteo remains the labeled current-condition fallback and seven-day forecast provider.
- Weather refresh uses network access but **zero AI calls**.
- Weather and seasonal context remain available to deterministic Executive Briefing context.
- Weather still cannot automatically reschedule projects, appointments, or work.
- Google Calendar remains intentionally deferred.

## Existing Library / Programs safeguards retained

Drop Box → Incoming Materials → Human Cataloging Desk approval → Trusted Library → Local Text Index → Librarian → Programs Library First → Chief final review → Human approval → Programs Auto-Archive.

The Librarian has **no direct web access**. Local document indexing and Programs Auto-Archive perform **zero AI calls**. Programs Auto-Archive runs only after final human package approval; Changes Requested archives nothing.

## Upgrade

Target schema: `0.8.6.9.5`. The upgrade is additive.

1. Extract v0.8.6.9.5 into a new folder.
2. Run `IMPORT DATA FROM PREVIOUS VERSION.bat`.
3. Point it at your working **v0.8.6.9.4** folder.
4. Start v0.8.6.9.5 normally.
5. Keep v0.8.6.9.4 untouched until this build passes your real-world test.

The importer carries `.env`, `mavis.db`, `repository/`, and `library/` while leaving the new application/world code intact. Existing People and Work Sessions are upgraded additively.

## Still deferred

Google Calendar integration, automatic day/week scheduling, automatic weather-driven rescheduling, Medicaid qualification/rules mapping, automatic government submission, grant reporting rules, Vernadette's grant system, volunteer scheduling, payroll, NWS alert automation, long-term PWS history import, scanned-document OCR, and fully automatic public publishing remain intentionally deferred in v0.8.6.9.5.

## Existing operational safeguards

AI Activity + Cost Controls remain enabled. Role routing **does not silently transmit the work to another AI vendor** when the selected provider fails. Incoming material is **not a trusted Library item** until human Cataloging Desk approval. Incoming material **does not appear in Card Catalog search** until it is approved into the trusted Library.

Google Calendar is intentionally not included in this release. **live weather access** remains isolated to the Weather subsystem; it does not grant the Librarian web access, scheduling authority, or external-action authority.

Poe's conversational timekeeping is a local deterministic parser, not a new AI-delegated role. It does not broaden the Librarian's network access or authorize external action.

Initial plan approval does not trigger Programs Auto-Archive. Revision-plan approval does not trigger Programs Auto-Archive. Only the final human package approval can archive Programs-created outputs.

Programs Auto-Archive continues to perform zero AI calls and zero network calls; weather networking and Poe command parsing remain separate subsystems.

## v0.8.6.9.4 — Poe Work Hours Reports + CSV

This small release completes the first useful reporting loop for Poe's People & Work ledger without adding a new AI role or changing the core project workflow.

- Adds a dedicated **Work Hours Report** reachable from Poe's People panel.
- Filters completed work by **date range, person, participation type, activity category, and project/program**.
- Shows totals by **month, person, activity, participation type, and project/program**.
- Exports the exact filtered ledger to **CSV** for grant, nonprofit, and external reporting workflows.
- Uses the Campus timezone for date grouping. Open sessions are excluded until clocked out.
- Keeps the existing work-session audit trail and correction flow unchanged.

## v0.8.6.9.3 — Poe Operations + People & Work Hours

This is a deliberately small operations-foundation release built on the stable v0.8.6.9.2 baseline.

- Adds **Poe — Operations & Volunteer Coordinator** as a real Campus staff record with a provisional black/purple map marker until his canonical sprite is created.
- Adds a durable **People ledger** for volunteers, staff, board members, contractors, collaborators, and other helpers.
- Adds **Work Sessions** with clock-in/clock-out, participation type (Volunteer / Learning / Paid), optional project association, notes, and activity category.
- Seeds the first Mavis activity taxonomy: Administration; Education & Program Delivery; Research & Archives; Farm & Land Stewardship; Animal Care; Maintenance & Infrastructure; Grants & Development; Community Outreach; Media & Communications; Planning & Governance; Training & Learning; Volunteer Coordination; Other.
- Adds a durable **work-session audit trail**. Corrections preserve the prior history instead of silently replacing it.
- Keeps people/work records outside Demo Reset so operational records are not discarded with project-demo data.
- Does **not** yet add Medicaid eligibility logic, grant reporting rules, natural-language Poe commands, volunteer scheduling, payroll, or automatic government reporting. Those should be layered on only after this foundation is proven stable.

## v0.8.6.9.2 — Canonical Agent Names

This is intentionally a small operating-model step. It does **not** add new agent workflows yet. It preserves the stable internal workflow IDs while updating the four existing visible staff identities:

- Stella — Chief of Staff (`chief`)
- Percy — Director of Programs & Education (`programs`)
- Rose — Director of Research & Archives (`research`)
- Stewart — Land Steward (`caretaker`)

The existing weather, moon, Library First, project workflow, approvals, and AI routing remain unchanged. **Poe is added in v0.8.6.9.3 as an operations/timekeeping foundation but is not yet an AI-delegated workflow role. Vernadette remains deferred until the grants foundation is added safely.**

## Previous v0.8.6.9.1 foundation — Pond Weather Widget + Moon Cycle

- Adds a compact, clickable Weather at Mavis window beside the pond on the Campus world.
- Shows current observed temperature/condition, today's high/low, precipitation chance, wind, and the honest current-source label (KWFLATT11 when PWS data is active).
- Adds a local moon-cycle calculation: phase, icon, illumination, moon age, approximate next full moon, and approximate next new moon.
- Moon calculations use zero network calls and zero AI calls.
- Clicking the pond widget opens the full Weather & Seasons drawer.
- The widget is isolated from the buildings/agents rendering layers; the canonical v0.8.6.8.1 world shell remains intact.
- Weather and moon information are read-only planning context. They cannot reschedule work or grant the Librarian network access.


## v0.8.7.4.2 — Living Campus Movement + Animated Weather HUD
- Available staff now take real cross-campus walks using the established path graph instead of only nudging around their home building.
- Percy/Poe and Stella/Vernadette can occasionally walk together when both are free. Ambient visits are visual/social only and never create fake tasks, work hours, or activity records. Real assignments immediately override ambient movement.
- Current weather and moon are tucked farther into the upper-left map corner in a compact framed HUD. The weather scene animates locally with CSS (sun, drifting clouds, rain, snow, fog, or lightning) and shows current temperature/summary.
- Clicking either weather or moon still opens Weather & Seasons. No new network or AI calls are added by the animation.
