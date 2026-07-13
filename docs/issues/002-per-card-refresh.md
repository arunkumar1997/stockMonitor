# Issue #002 — Per-card refresh button on `StockCard`

**Type:** feature
**Severity:** minor (UX enhancement)
**Area:** frontend
**Reporter:** CEO
**Triaged by:** Remy (Producer)
**Assignee:** Nova (Frontend)
**Depends on:** none — backend + API wrapper already exist

---

## Request

> "I need the ability to refresh a single stock, so we can have one refresh icon per card when it's expanded."

Add a **refresh icon on each `StockCard`** that triggers a refresh for only that stock, rather than forcing the user to hit the global refresh (which re-fetches everything).

## What already exists (don't rebuild)

- **Backend endpoint:** `POST /api/scheduler/refresh/{symbol}` — [backend/main.py#L189-L203](backend/main.py#L189-L203). Kicks off a background `scheduler.refresh_one` thread and returns immediately.
- **Frontend API wrapper:** `forceRefresh(symbol)` — [frontend/src/api.js#L32-L33](frontend/src/api.js#L32-L33).

So Nova only needs to wire the UI.

## Scope clarification

The wording "when it's expanded" is slightly ambiguous. Current UI: cards have **no per-card collapse state** — they render fully whenever their parent `SectorSection` is expanded (see [Dashboard.jsx#L129-L136](frontend/src/components/Dashboard.jsx#L129-L136)).

**Default interpretation (build this):** always render the refresh icon in the `StockCard` header, next to the existing delete icon — [StockCard.jsx#L232-L245](frontend/src/components/StockCard.jsx#L232-L245). The card is only mounted while its sector is expanded, so this naturally satisfies "when it's expanded".

If the CEO actually wants a new per-card collapse/expand feature, that's a separate issue — flag it back to Remy before building.

## Requirements

- [ ] Add a `RefreshIcon` `IconButton` on `StockCard`, positioned to the **left of the delete icon** in the header action cluster.
- [ ] `onClick` calls `forceRefresh(stock.symbol)` from [api.js](frontend/src/api.js).
- [ ] While the request is in flight (and for a short window after — e.g. until the next dashboard poll returns fresh data for this symbol), show a **spin animation** on that card's refresh icon and **disable** the button to prevent double-clicks.
- [ ] Show a toast on success (`enqueueSnackbar(\`Refreshing ${symbol}…\`, { variant: "info" })`) and on failure (`variant: "error"`).
- [ ] Do **not** block the whole dashboard while a single card refreshes. State must be local to the card.
- [ ] Tooltip: `"Refresh this stock"`.
- [ ] Icon color / border style should match the existing header refresh button in `Dashboard` for visual consistency, but scaled down to card-header size.

## Coordination with Issue #001

Issue #001 will introduce `React.memo` on `StockCard`. Make sure the new refresh state (`isRefreshing`) stays **local to `StockCard`** so it doesn't defeat memoization. Do **not** lift it to `Dashboard`.

Reuse the shared `spin` keyframe once #001 moves it out of inline `sx` — do not add a second inline `@keyframes spin` on the card.

## Nice-to-have (only if trivial)

- [ ] After `forceRefresh` succeeds, trigger a short `setTimeout` (~3 s) then re-fetch just this card's data via `analyzeStock(symbol)` and update the card locally, so the user sees fresh numbers without waiting for the next global poll. If the endpoint returns 202 (not cached yet), retry once after another 2 s. Cap at 2 retries then give up silently.

## Out of scope

- Per-card collapse/expand toggle (file a separate issue if wanted).
- Changing the global refresh button behavior.
- Backend changes — the endpoint is ready.

## Success criteria

- Clicking the per-card refresh icon triggers exactly one `POST /api/scheduler/refresh/{symbol}` call (verify in Network tab).
- The refresh icon spins on that card only. Other cards are unaffected — no re-renders on other cards (verify with React DevTools Profiler).
- Rapid double-clicks do not fire two requests.
- Global "Refresh now" button in the header still works unchanged.

## Branch / PR

- Branch: `feat/per-card-refresh`
- PR title: `feat: add per-card refresh button on StockCard (Closes #002)`
- Merge order: **after** Issue #001 is merged, so Nova can reuse the shared `spin` keyframe and doesn't create sx churn on a soon-to-be-memoized component.
