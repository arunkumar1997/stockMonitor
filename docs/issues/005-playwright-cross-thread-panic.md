# Issue #005 — Playwright cross-thread panic on manual refresh

**Type:** bug
**Severity:** blocker (all data fetches after startup fail; dashboard freezes on stale data)
**Area:** backend
**Reporter:** CEO
**Triaged by:** Remy (Producer)
**Assignee:** Sage (Backend)

---

## Symptom

Every manual refresh (per-card or global) returns HTTP 200 but the fetch fails silently in the background. Backend logs:

```
[scheduler] [MOTHERSON.NS] ℹ Starting refresh …
INFO:     127.0.0.1:48870 - "POST /api/scheduler/refresh/MOTHERSON.NS HTTP/1.1" 200 OK
[scheduler] [MOTHERSON.NS] ℹ Fetching 6mo OHLCV history …
[fetcher] History error for MOTHERSON.NS: cannot switch to a different thread (which happens to have exited)
[scheduler] [MOTHERSON.NS] ⚠ No price history returned — skipping
```

Reproducer:
```bash
# Any manual refresh, any symbol, after the app has been running for a few seconds:
curl -X POST http://localhost:8000/api/scheduler/refresh/MOTHERSON.NS
```

## Root cause

Playwright's **sync API is greenlet-based and pins its event loop to the OS thread that called `sync_playwright().start()`.** Any call on the resulting browser object from a **different** OS thread raises `cannot switch to a different thread (which happens to have exited)`.

Current architecture creates the mismatch by design:

1. **Startup check** ([backend/main.py#L30-L47](backend/main.py#L30-L47)) spawns a daemon thread `playwright-check` that calls `fetcher._get_browser()`. The browser singleton is bound to that thread. The thread returns immediately after the check succeeds → thread exits → its underlying event loop is torn down.

2. **Every refresh** ([backend/main.py#L189-L203](backend/main.py#L189-L203) and add-stock / restore-stock paths) spawns a *new* `threading.Thread(target=scheduler.refresh_one, …)`. That thread calls `_get_browser()`, gets the cached `_browser` (bound to the now-dead `playwright-check` thread), and tries to `browser.new_context(...)` → cross-thread → panic.

3. Even without the startup check, `refresh_all` runs on APScheduler's job thread while ad-hoc refreshes run on `main.py`'s fire-and-forget threads → **two different threads, same singleton browser** → same bug.

Why did #003's verification pass? Because MOTHERSON.NS was refreshed within a few hundred ms of the startup check completing — the daemon thread's greenlet loop may not have been fully torn down yet. It's a race. Under any real usage the bug reproduces immediately.

## Fix plan (Sage)

Adopt the **single dedicated worker thread + job queue** pattern. All Playwright work happens on one thread; the browser singleton stays pinned to that one thread forever.

### Must-fix

- [ ] Add a `queue.Queue` (`_refresh_queue`) and a single daemon worker thread `_refresh_worker` in `backend/scheduler.py`, started from `scheduler.start()`.
- [ ] `refresh_one(symbol, name, sector, *, skip_if_fresh=False)` becomes a **thin enqueuer** — puts a job dict on the queue and returns immediately. Sentinel `None` signals worker shutdown.
- [ ] Extract the current body of `refresh_one` into `_do_refresh_one(...)` (same signature). The worker loop pops jobs and calls `_do_refresh_one` sequentially.
- [ ] `refresh_all` (APScheduler job) enqueues one job per active stock rather than iterating synchronously. Keeps polite delays *inside* the worker loop, not the scheduler thread.
- [ ] Remove the `threading.Thread(target=scheduler.refresh_one, ...).start()` wrapping in `backend/main.py`'s three call sites (add-stock, restore-stock, force-refresh). Just call `scheduler.refresh_one(...)` directly — it's now non-blocking.
- [ ] Move `scheduler.stop()` to also send the `None` sentinel and `join()` the worker with a small timeout so shutdown is clean.

### Should-fix (fetcher / startup)

- [ ] **Delete the startup Playwright-launch check from `backend/main.py`.** It's the primary trigger of this bug and gives false confidence. Replace with a **binary-existence check** only (verify `~/.cache/ms-playwright/chromium*/chrome-headless-shell*` exists, or `python -m playwright install --dry-run` returns 0). Keep `playwright_ok` in `/health` but sourced from the binary check, not a browser launch.
- [ ] Optional: after the worker starts, enqueue a synthetic "warmup" job that just calls `_get_browser()` on the worker thread so the first user-triggered refresh doesn't pay the ~2 s launch cost. Keep this fully optional / behind a config flag.

### Nice-to-have

- [ ] Expose queue depth in `/api/scheduler/status` (`queued`, `in_flight_symbol`) so the UI can show "5 stocks queued" during a full refresh.
- [ ] Add a small integration test that hammers `POST /api/scheduler/refresh/*` for 3 different symbols in rapid succession and asserts all three complete without a cross-thread error. (Skip if repo has no test infra yet.)

## Success criteria

- After the app has been running > 30 s (well past any startup-check race window), `curl -X POST http://localhost:8000/api/scheduler/refresh/MOTHERSON.NS` produces the full success log path (`Signal=X (Y%) | Valuation=… | Done in Ns`), not the "cannot switch to a different thread" error.
- Adding a new stock (`POST /api/stocks`) still triggers a background fetch that completes successfully.
- `refresh_all` (APScheduler tick) completes normally.
- `GET /api/scheduler/status.last_fetch_status[SYMBOL]` shows `{"status": "ok", …}` for the manually refreshed symbol.
- No regression to per-card refresh from #002.

## Out of scope

- Rewriting fetcher to async Playwright.
- Adding retry / backoff (separate concern).
- Concurrency > 1 (single worker is the point of the fix — parallel Playwright is a whole separate design).

## Branch / PR

- Branch: `fix/playwright-cross-thread-worker`
- PR title: `fix: serialize Playwright calls on a single worker thread (Fixes #005)`
- Split commits suggestion:
  1. `refactor(scheduler): extract _do_refresh_one from refresh_one`
  2. `fix(scheduler): serialize fetches through a single worker thread + queue (Fixes #005)`
  3. `fix(main): remove per-request threading.Thread wrapping; refresh_one now non-blocking`
  4. `fix(main): replace live Playwright launch check with binary-existence check`
- **Priority: blocker** — every user-triggered refresh is failing. Ship this before touching new features.
