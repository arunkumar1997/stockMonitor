# Issue #007 — Migrate scheduler status updates from polling to SSE

**Type:** refactor / performance
**Severity:** minor (architectural cleanup — user-invisible)
**Area:** backend + frontend (cross-stack)
**Reporter:** CEO
**Triaged by:** Remy (Producer)
**Assignee:** Sage (backend) + Nova (frontend) — coordinated
**Depends on:** #005 (merged — `last_fetch_status` on backend), #006 (merged/in-flight — StockCard poll)

---

## Motivation

Three separate places in the app currently poll `GET /api/scheduler/status` or `/api/logs`:

1. [frontend/src/components/Dashboard.jsx](frontend/src/components/Dashboard.jsx) — polls `/api/scheduler/status` for the header "fetching X" chip.
2. [frontend/src/components/LogsPanel.jsx](frontend/src/components/LogsPanel.jsx) — polls `/api/logs` every 2 s while open.
3. [frontend/src/components/StockCard.jsx](frontend/src/components/StockCard.jsx) — added in #006, polls `/api/scheduler/status` every 2 s while the card is refreshing.

That's N pollers per tab (N grows with active spinners) plus per-panel pollers. Each is fine in isolation; together they're duplicated work and up to 2 s stale.

The right shape here is **server-sent events**: the backend already knows exactly when the interesting things happen (job dequeued, fetch started, fetch completed with `{status, message, ts}`, log line appended). It should push those events instead of the browser guessing at intervals.

## Why SSE, not WebSocket

- Traffic is **one-way, server → client**. No commands are sent back over the same channel.
- `EventSource` is native in every modern browser, ~5 lines to consume, auto-reconnects on disconnect (uvicorn reload, laptop-sleep, network flap).
- Backend integration is minimal: `sse-starlette` streams from an `asyncio.Queue` fed by a threadsafe bridge from the scheduler worker.
- WebSocket adds bidirectionality we don't need, plus handshake/subprotocol/close-code complexity.

## Design

### Backend

1. Add `sse-starlette` to [backend/requirements.txt](backend/requirements.txt).
2. In [backend/scheduler.py](backend/scheduler.py), add a module-level list of `asyncio.Queue` subscribers guarded by a lock, plus a helper `_emit(event: dict)` that:
   - Copies the event dict.
   - Iterates subscribers and puts the event onto each queue via `loop.call_soon_threadsafe(q.put_nowait, event)` (the scheduler worker runs in a plain `threading.Thread`, subscribers live in the FastAPI event loop, so we must cross the boundary correctly).
3. Emit events at the natural transition points inside `_refresh_worker_loop` / `_do_refresh_one`:
   - `{"type": "fetch_started",   "symbol": "...", "queued": N, "ts": iso}`
   - `{"type": "fetch_finished",  "symbol": "...", "status": "ok"|"error", "message": "...", "ts": iso, "queued": N}`
   - `{"type": "log",             "level": "INFO"|..., "symbol": "...", "message": "...", "ts": iso, "id": seq}`
   - `{"type": "status_snapshot", …}` — sent once on new subscriber connect so the client doesn't need a separate GET.
4. Add a new endpoint in [backend/main.py](backend/main.py): `GET /api/scheduler/events` returning an `EventSourceResponse` (from `sse-starlette`). On connect: create a fresh subscriber `asyncio.Queue`, emit a `status_snapshot`, then `yield` messages forever until the client disconnects (at which point remove the queue from the subscriber list — `finally` block).
5. Keep `GET /api/scheduler/status` and `GET /api/logs` **exactly as-is** — they remain the source of truth for one-shot queries, tests, health checks, and clients that don't do SSE. No shape change, no deprecation.

### Frontend

1. Add a small `useSchedulerEvents()` hook in a new file `frontend/src/hooks/useSchedulerEvents.js`:
   - Opens a single `EventSource("/api/scheduler/events")` on mount, closes on unmount.
   - Exposes the latest `status` object (last-known scheduler status derived from all events) plus a `subscribe(type, handler)` API for consumers that want raw events.
   - Handles `EventSource`'s built-in reconnection quietly. Logs a single console warning after N consecutive failures.
2. Refactor the three consumers to use the hook:
   - `Dashboard` — reads `status` from the hook for the header chip instead of `useEffect(() => setInterval(getSchedulerStatus, 5000))`.
   - `LogsPanel` — subscribes to `type === "log"` events and appends to its buffer. Falls back to a one-shot `GET /api/logs` on first mount for backfill.
   - `StockCard` — subscribes to `type === "fetch_finished" && symbol === thisSymbol`. Replaces the 2 s poll+preTs pattern from #006 with a single event handler. Keep the 60 s safety timeout as a defence-in-depth net.
3. Remove the now-redundant `setInterval` calls from the three consumers.
4. `useSchedulerEvents` MUST be memoized/stabilized so it doesn't break `React.memo` on `StockCard` — probably best expressed as a **provider at the `Dashboard` root** (`SchedulerEventsProvider`) with a `useLastFetchStatus(symbol)` selector hook that only re-renders subscribing cards when their specific symbol's status changes. Otherwise every event re-renders every card and we undo #001.

### Testing

- Backend: add one integration test that opens the SSE stream, triggers a `POST /api/scheduler/refresh/{symbol}`, and asserts a `fetch_started` followed by a `fetch_finished` event with the same symbol. Skip if the repo lacks pytest infra — file as a follow-up in that case.
- Frontend: Ivy sign-off — see below.

## Must-fix / Should-fix / Nice-to-have

### Must-fix
- [ ] Backend `GET /api/scheduler/events` SSE endpoint that emits `fetch_started`, `fetch_finished`, `log` events.
- [ ] `useSchedulerEvents` hook + `SchedulerEventsProvider` on frontend.
- [ ] `StockCard` refresh gating switches to event-driven completion (removes the 2 s poll from #006; keeps the 60 s safety timeout).
- [ ] `Dashboard` header chip switches to hook.
- [ ] `LogsPanel` switches to hook.
- [ ] `sse-starlette` added to `requirements.txt`.
- [ ] Existing `GET /api/scheduler/status` and `GET /api/logs` endpoints **not** removed — they remain valid one-shot queries.

### Should-fix
- [ ] Handle uvicorn `--reload`: on reconnect after a server restart, `EventSource` will auto-reconnect and receive a fresh `status_snapshot`, so the UI should self-heal within seconds. Sanity-check this works.
- [ ] Emit `queue_updated` events so multiple consumers can show queue depth without recomputing it.

### Nice-to-have
- [ ] SSE `last-event-id` support for resumable log streams (so `LogsPanel` doesn't lose messages during brief disconnects).
- [ ] Configurable heartbeat (`sse-starlette` default is 15 s ping) to keep proxies from timing out.

## Success criteria

- Backend: `curl -N http://localhost:8000/api/scheduler/events` opens a stream that immediately receives a `status_snapshot`, then subsequent `fetch_started`/`fetch_finished` events for any refresh triggered from another shell.
- Frontend: with DevTools Network → Filter by "Fetch/XHR", after page load and during a per-card refresh + backend fetch cycle, there are **0** `GET /api/scheduler/status` requests and **0** `GET /api/logs` requests (aside from the one-time `LogsPanel` mount backfill). Instead exactly one persistent `GET /api/scheduler/events` connection.
- StockCard spinner clears **within ≤ 1 s** of the backend `Done in Ns` log line (down from ≤ 2 s in the poll implementation).
- `React.memo` on `StockCard` is still doing its job: idle-tab 5 s CDP trace shows 0 `UpdateLayoutTree` events on cards not involved in any fetch — same acceptance signal as #001.
- Kill backend mid-refresh → `EventSource` auto-reconnect kicks in ≤ 3 s after backend comes back → UI catches up to the current state via the fresh `status_snapshot`.

## Out of scope

- Bidirectional messaging (WebSocket).
- Auth on the SSE endpoint (same posture as the rest of the API today).
- Push notifications for market events / price alerts — that's a whole product feature, not this ticket.
- Migrating `POST /api/scheduler/refresh/{symbol}` or other write endpoints (they stay REST).

## Branch / PR

- Branch: `feat/scheduler-sse`
- PR title: `feat: server-sent events for scheduler status + logs (Fixes #007)`
- Suggested split commits (single PR, but reviewable in slices):
  1. `chore(deps): add sse-starlette`
  2. `feat(scheduler): thread-safe event bus + emit fetch_started/finished/log events`
  3. `feat(api): GET /api/scheduler/events SSE endpoint`
  4. `feat(fe): useSchedulerEvents hook + SchedulerEventsProvider`
  5. `refactor(dashboard): consume scheduler-events hook instead of polling`
  6. `refactor(logs): consume scheduler-events hook; drop 2s poll`
  7. `refactor(stockcard): gate refresh spinner on fetch_finished event (Fixes #007)`

## Rationale (why this instead of keeping polling)

- **Unifies three duplicate polling loops** into one connection, one code path, one place to reason about lifecycle.
- **Zero-latency completion** — spinner clears the instant the backend finishes, not on the next 2 s tick.
- **Zero busywork when idle** — no requests while nothing is happening.
- **Future-friendly** — any new consumer (a mini stock ticker, a live price alert) plugs into the same event bus.

The current polling is **not broken**; #006 solved the user-visible bug correctly. This is deliberate architectural cleanup, not a bug fix. Priority: after any active user-visible work.
