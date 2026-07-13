# QA Sign-off — Issue #007 (feat/scheduler-sse)

**Reviewer:** Ivy (QA)
**Date:** 2026-07-13
**Branch:** `feat/scheduler-sse` (local-only, 7 commits ahead of `main`; **also has ~698 lines of uncommitted formatting changes in the working tree — see "Notes for Remy" at the bottom**)
**Verdict:** ✅ **PASS — safe to push / merge**

---

## Commit range tested

```
3bb3ef7 refactor(stockcard): gate refresh spinner on fetch_finished event (Fixes #007)
74f7993 refactor(logs): consume useSchedulerLogs; drop 2s poll
30d289f refactor(dashboard): consume useSchedulerStatus hook instead of polling
fa4eb3d feat(fe): useSchedulerEvents hook + SchedulerEventsProvider
1126a7d feat(api): GET /api/scheduler/events SSE endpoint
4edd3e6 feat(scheduler): thread-safe event bus + emit fetch_started/finished/log events
28bafc5 chore(deps): add sse-starlette==2.1.3
```

## Environment

- Backend: `./start_backend.sh` (uvicorn on :8000)
- Frontend: `./start_frontend.sh` (Vite dev on :5173)
- Browser: headless Chromium (Playwright 1.59) at 1440×900
- Data: 45 watchlist rows / cached data for 6 of them (rest have no cached data → cards still render, "Refresh" fetches live from Yahoo Finance which takes 25-35 s per symbol)
- Drivers:
  - Main: [_playthrough_007.py](_playthrough_007.py) — T1–T5, T7, T8
  - Focused T7 (better row-count selector): [_t7_only.py](_t7_only.py)
  - Focused T6 (SSE reconnect): [_t6_reconnect.py](_t6_reconnect.py)

## Console health across full run

`0` console errors, `0` warnings, `0` page errors, `0` network failures during T1–T5, T7, T8.
`1` console error during T6 (kill-backend step) — see T6 notes; **expected** and not an app bug.

## Test results

| # | Test | Measurement | Verdict |
|---|---|---|---|
| **T1** | Zero polling in 15 s steady-state idle | `GET /api/scheduler/status` = **0**, `GET /api/logs` = **0**, `EventSource GET /api/scheduler/events` connections = **1**. Window measured = 12.85 s (network log timing). No polling of any kind during idle. | ✅ **PASS** |
| **T2** | 5 s idle CDP trace (#001 regression) | `UpdateLayoutTree=0`, `Layout=5`, `Paint=10`, `ScheduleStyleRecalculation=0`, `TimerFire=5`, `FunctionCall=25`, long tasks > 50 ms = **0**. Identical to the #001 sign-off numbers to the digit — the SSE rewrite did not re-introduce full-tree rerenders. | ✅ **PASS** |
| **T3** | Per-card MOTHERSON.NS refresh completes via SSE (no polling) | `POST /api/scheduler/refresh/MOTHERSON.NS` = **1**, status polls during refresh = **0**, log polls during refresh = **0**. Spinner engaged + button disabled at click (`{disabled: true, anim: "spin"}`). Spin cleared and button re-enabled at **30 078 ms** after click — well under the 60 s safety timeout. Backend log for the same click reports `Done in 30.x s` for MOTHERSON.NS ⇒ spinner cleared within ≤ 1 s of the backend Done log, meeting ticket criterion. | ✅ **PASS** |
| **T4** | Spam-click regression: 5 clicks while a card is spinning | 1 real click + 5 JS-dispatched clicks = **1** `POST /api/scheduler/refresh/{symbol}`. The `disabled` attribute plus `mountedRef` gating both work; #006 debounce is preserved. | ✅ **PASS** |
| **T5** | Two-tab test (cross-tab SSE fan-out) | Tab 2 opened its own `GET /api/scheduler/events` connection (**1** EventSource per tab). Refresh triggered in tab 1; tab 2 observed the header "⟳ fetching HDFCBANK.NS" chip appear *and* clear after completion, driven entirely by its own SSE stream. Tab 2 fired **0** `GET /api/scheduler/status` and **0** `POST /api/scheduler/refresh/*` during the flow. Tab 1 stayed fully functional after tab 2 was closed. Elapsed: 30.9 s (matches backend fetch duration). | ✅ **PASS** |
| **T6** | SSE auto-reconnect after backend restart | Killed backend via `fuser -k`; backend confirmed dead in 2.12 s. Restarted; became reachable in 0.45 s. Browser `EventSource` reconnected within **1.0 s** of the port coming back up (new `GET /api/scheduler/events` request observed in network log). Post-reconnect functional test: clicked a per-card refresh, spinner cleared via SSE in 32.9 s — proving the fresh SSE stream is delivering `fetch_finished` events, not that the 60 s safety timeout fired. Header chip empty after restart (no orphaned in-flight state). One console error: `Failed to load resource: net::ERR_INCOMPLETE_CHUNKED_ENCODING` — this is the browser's expected report of the terminated SSE stream at kill time; standard behaviour, not an app bug. | ✅ **PASS** |
| **T7** | LogsPanel Clear / Pause / Resume + backfill-once | On open: **1** `GET /api/logs?limit=200` (backfill), 128 rows rendered. Live refresh → **0** additional `/api/logs` GETs, 9 new rows arrive via SSE (128 → 137). **Pause** → rows freeze at 137 across a full refresh cycle (backend continued emitting events; UI display did not change). **Resume** → panel caught up: 137 → 146 (paused-period entries backfilled correctly). **Clear** → visible rows drop to 0; a fresh refresh after Clear adds 9 new rows (0 → 9) — Nova's floor-id semantics correctly show only new-since-clear entries. | ✅ **PASS** |
| **T8** | Global "Refresh now" | Global refresh icon found. During a 91 s observation window: **0** `GET /api/scheduler/status` polls, **0** `GET /api/logs` polls, **2** `GET /api/dashboard` requests (one from the click's `fetchDashboard(true)`, one from the pre-existing 30 s auto-refresh interval — both legit REST calls unaffected by #007). Concurrent per-card spinners during flow = **0** (correctly, the global button never triggers per-card `isRefreshing` state — that stays local to explicit per-card clicks, coordination with #002 intact). Header "⟳ fetching X" chip was not observed to cycle — see caveat in "Findings" below; this is because the header "Refresh now" button in the current implementation only re-fetches the dashboard display (no backend queue is triggered), not a #007 regression. | ✅ **PASS** |

## Overall verdict

✅ **PASS — safe to push / merge.**

All eight watch-points are green. In particular:

- **T2 is the flagship check** — the SSE rewrite did **not** regress #001 memoisation. Idle CDP trace numbers are byte-identical to the #001 sign-off (0 `UpdateLayoutTree`, 5 `TimerFire`, 5 `Layout`, 10 `Paint`, 0 `ScheduleStyleRecalculation`, 0 long tasks). Nova's `useSyncExternalStore` + reference-preserving store design does exactly what the ticket asked.
- **T1 + T3 together** prove the polling is genuinely gone: idle window has zero status/log GETs, and an active per-card refresh also has zero — completion signal comes strictly from the SSE `fetch_finished` event.
- **T5 + T6** validate the multi-consumer and fault-tolerance stories: cross-tab fan-out works with one EventSource per tab (no shared-worker complexity needed), and the native browser auto-reconnect kicks in cleanly ≤ 1 s after backend recovery.
- **T7** is the most nuanced check and everything landed: backfill-once, live push, pause snapshot, resume catch-up, and clear-with-floor all work per Nova's design notes.

## Findings / notes

### T8 caveat (not a bug)
The ticket describes T8 as "header 'fetching X' chip cycles through symbols … driven by `fetch_started` events". My measurement shows **0** chip cycles observed. Investigation: the header **Refresh now** button (`onRefresh={handleRefresh}` → `fetchDashboard(true)` in [Dashboard.jsx#L270](../../frontend/src/components/Dashboard.jsx#L270)) only re-issues `GET /api/dashboard` — it does not `POST` anything to enqueue backend fetches. There is no `/api/refresh_all` backend endpoint. So the scheduler queue stays empty, no `fetch_started` events fire, and correspondingly no chip appears — **which is correct behaviour for this button**. This matches the pre-#007 behaviour recorded in the [#002 sign-off's T6 network log](002-signoff.md) (`GET /api/dashboard` + `GET /api/scheduler/status`, no POST).

What #007 *did* change is that the old `GET /api/scheduler/status` companion poll from that button is now **gone**, replaced by pure SSE — that's the improvement the ticket promised, and my measurement confirms it (`status_polls_during_flow = 0`).

The T5 flow (per-card refresh, chip appears in the other tab) is what actually validates the "chip cycles via `fetch_started`" contract — that test is green.

### T6 console error (expected)
`Failed to load resource: net::ERR_INCOMPLETE_CHUNKED_ENCODING` fires when the SSE stream is force-terminated by killing the backend. This is the browser's standard way of reporting a broken stream; it does not indicate an app bug. The `EventSource.onerror` handler in `SchedulerEventsProvider` catches this and lets the browser auto-reconnect (verified: reconnected within 1 s of backend restart).

### Uncommitted working-tree changes
Nova has committed 7 well-scoped commits. **The working tree, however, has ~698 lines of *additional* uncommitted formatting-only changes** (prettier-style reformatting of `Dashboard.jsx`, `LogsPanel.jsx`, `StockCard.jsx`, `useSchedulerEvents.js`, and a 4-line style-only diff in `SchedulerEventsProvider.jsx`, plus a cosmetic line-wrap in `backend/scheduler.py`). `git diff -w` still shows meaningful line counts, so these are line-wrap reformats (single-line object literals expanded to multi-line), not pure whitespace. I tested against the **working-tree** state — that's what actually runs — and it passes.

Before pushing, Nova should either (a) `git commit --amend` these into the last commit, or (b) squash them into a separate `style: prettier reformat` commit and confirm the diff is truly no-op. If they're truly zero-behaviour changes (which my black-box testing suggests), option (a) is fine.

### Nit (not filed as issue)
- Only 6 of the 45 seeded stocks had cached data at test start, so most cards showed skeleton fundamentals. Not a #007 concern; would flag separately if it matters.

## Follow-ups filed

**None.** No regressions. No bug files created. Existing follow-ups from #001 (issue #004) and prior sprints are unrelated.

## Artifacts

- Sign-off (this file): `docs/qa/007-signoff.md`
- Playthrough drivers: [_playthrough_007.py](_playthrough_007.py), [_t7_only.py](_t7_only.py), [_t6_reconnect.py](_t6_reconnect.py)
- Raw perf data: `docs/qa/007-perf-raw.json` *(local only, not tracked)*
- Screenshots + CDP trace: `docs/qa/screenshots/007/` *(local only — covered by chore/qa-artifacts `.gitignore`, findings summarised inline)*

## Notes / surprises for Remy

- **The "networkidle" navigation strategy no longer works.** Because SSE keeps one long-lived connection open, Playwright's `wait_until="networkidle"` never fires. I fell into this on the first driver attempt and switched to `wait_until="domcontentloaded"`. Trivial for scripts; worth flagging so Nova / anyone else writing e2e tests avoids the pitfall.
- **Real yfinance fetches take 24-35 s each in this environment.** The safety timeout in `StockCard` is 60 s, which is comfortable but tight if Yahoo throttling worsens. Not a #007 concern; the *only* thing #007 changed here is *how* the client learns of completion (SSE push instead of 2 s poll). Every T3-style measurement confirms SSE actually fires within ≤ 1 s of backend `Done in Ns`.
- **`pkill -f 'uvicorn main:app'` is unreliable for uvicorn --reload** — the reloader spawns worker(s) as multiprocessing forks whose full command line is `python -c "from multiprocessing.spawn import ..." --multiprocessing-fork` which doesn't match. Use `fuser -k 8000/tcp` for a clean kill. Consider adding that to a QA doc or dev script.
- **Merge order:** `feat/scheduler-sse` builds atop the already-merged-or-in-flight #001/#002/#005/#006 line. All prior work is preserved (T2 memoization intact, T4 spam-click debounce intact). Nothing prevents merging this once Nova commits the formatting delta.
