# Issue #006 — Per-card refresh re-enables before the actual fetch completes

**Type:** bug
**Severity:** major (UX / correctness — allows duplicate refresh jobs to enqueue)
**Area:** frontend
**Reporter:** CEO
**Triaged by:** Remy (Producer)
**Assignee:** Nova (Frontend)
**Depends on:** #005 (merged — backend now exposes `last_fetch_status[SYMBOL].ts` reliably)

---

## Symptom

Click the refresh icon on a `StockCard`. The icon spins and the button is disabled — good. **After ~3 seconds** the icon stops spinning and the button re-enables. **But the backend fetch is still running** (a real refresh takes ~25–30 s: history + news + fundamentals). During those extra 22–27 s the user can click refresh again and enqueue a redundant job.

CEO's words:
> "When I click refresh on card it starts refresh but refresh button also enabled again. Then user can refresh many times which is not good. I want to show refreshing icon and once refresh is done then only allow users to refresh again."

## Root cause

In [frontend/src/components/StockCard.jsx](frontend/src/components/StockCard.jsx) the per-card refresh handler added in #002 uses a **fixed 3-second timer** to clear `isRefreshing`:

```js
setTimeout(() => setIsRefreshing(false), 3000);
```

That was intentional as a **minimum-visible-spinner** heuristic in #002 (so the spinner wouldn't flash for a millisecond on fast responses). But the fetch itself is fire-and-forget on the backend — `POST /api/scheduler/refresh/{symbol}` returns 200 as soon as the job is *queued*, not when the fetch *completes*.

Since #005 merged, the backend exposes exactly the signal we need to fix this correctly: `GET /api/scheduler/status.last_fetch_status[SYMBOL]` returns `{"status": "ok" | "error", "message": str, "ts": ISO-8601}`. `ts` updates only when `_do_refresh_one` finishes for that symbol.

## Fix plan (for Nova)

Replace the fixed 3-second cosmetic clear with a **real completion signal** from the backend.

### Must-fix

- [ ] On click:
  1. Snapshot the current `last_fetch_status[SYMBOL].ts` (call it `preTs`; may be `undefined` for symbols never refreshed since server start — treat as `null`).
  2. Set `isRefreshing = true`, disable button, start spinner, show `info` toast (unchanged from #002).
  3. Call `forceRefresh(symbol)` — same as today.
- [ ] After the POST resolves, **poll `GET /api/scheduler/status` every 2 s** and check `last_fetch_status[SYMBOL]`:
  - If `ts` is present **and** `ts !== preTs` → refresh completed. Stop polling. Clear `isRefreshing`.
  - If `status === "ok"` → optional info toast (`Refreshed ${symbol}`) — keep it or drop; do not double-toast.
  - If `status === "error"` → `enqueueSnackbar("Refresh failed: <message>", { variant: "error" })`. Clear `isRefreshing`.
- [ ] **Safety timeout at 60 s.** If polling never sees a new `ts` (backend hang, network drop, worker stuck), clear `isRefreshing` anyway, stop polling, show a `warning` toast (`Refresh timed out — try again`). This prevents a permanently-disabled button.
- [ ] Also stop polling if the component unmounts (existing `mountedRef` pattern from #002 already covers `setIsRefreshing`; extend it to `clearInterval`/`clearTimeout` for the poller).

### Constraints (don't break #001 / #002)

- **Keep `isRefreshing`, `preTs`, the poll interval, and the safety timeout ALL local to `StockCard`.** Do not lift into `Dashboard`. Do not add props from parent. This preserves `React.memo` on `StockCard`.
- Do not add new dependencies. `axios` (or whatever `api.js` uses) + `setInterval` are enough.
- Do not change the visual behavior: same icon, same tooltip, same spinner style, same `<span>` wrapper for the disabled-tooltip trick.
- Do not modify the backend or the shared `api.js` beyond adding a tiny helper if useful.

### Should-fix

- [ ] Add a small helper `getSchedulerStatus()` to [frontend/src/api.js](frontend/src/api.js) that wraps `GET /api/scheduler/status` — currently the app calls this endpoint from `Dashboard` directly; centralising the call keeps `StockCard` clean.
- [ ] Poll interval should back off gently if the app tab is hidden: use `document.visibilityState === "hidden"` to skip a tick. Cheap improvement to avoid pointless polling in a background tab.

### Nice-to-have

- [ ] While polling, if `schedulerStatus.queued > 0 && schedulerStatus.current_symbol !== SYMBOL`, show a small text next to the spinner like *"Queued…"* vs. *"Fetching…"* — surfaces the serialised-worker behavior from #005. Only add if trivial; do not block on it.

## Success criteria

- Click refresh on card A → spinner + disabled button.
- Backend logs show `[scheduler] [A] Starting refresh …`.
- Spinner stays visible for the full backend fetch (~25–30 s), button stays disabled the whole time.
- Backend logs show `[scheduler] [A] ✓ Signal=… Done in Ns`.
- **Within ≤ 2 s of that log line**, the card's spinner stops and the button re-enables. No duplicate `POST /api/scheduler/refresh/A` requests are visible in the Network tab across the entire duration.
- Clicking refresh on card B while A is still spinning works normally (A keeps spinning; B enters its own spinner; both eventually clear when their respective `ts` values update).
- Kill the backend mid-refresh → spinner stops after ≤ 60 s with a warning toast, not stuck forever.

## Out of scope

- Changing the backend contract or `last_fetch_status` shape.
- Rewriting to WebSocket/SSE instead of polling (poll is fine here).
- Global "refresh all" button changes.
- Any per-card collapse feature.

## Branch / PR

- Branch: `fix/per-card-refresh-real-completion`
- PR title: `fix: gate per-card refresh spinner on real backend completion (Fixes #006)`
- Suggested split commits:
  1. `feat(api): add getSchedulerStatus() helper` (only if the should-fix helper is added)
  2. `fix(stockcard): gate isRefreshing on last_fetch_status.ts change (Fixes #006)`
