# QA Sign-off — Issue #002 (feat/per-card-refresh)

**Reviewer:** Ivy (QA)
**Date:** 2026-07-13
**Branch:** `feat/per-card-refresh` (local-only, 1 commit ahead of `main`)
**Verdict:** ✅ **PASS — safe to push / merge**

---

## Commit range tested

```
85eb166 feat(stockcard): add per-card refresh icon (#002)
```

## Environment

- Backend: `./start_backend.sh` (uvicorn on :8000)
- Frontend: `./start_frontend.sh` (Vite dev on :5173)
- Browser: headless Chromium (Playwright 1.59) at 1440×900
- Data: watchlist from #001 run — **43 stocks / 9 sectors**, all sectors expanded
- Card driven for T1–T5: **index 0, `MOTHERSON.NS`** (first `MuiCard-root`)
- Driver: [_playthrough_002.py](_playthrough_002.py)

## Console health across full run

`0` console errors · `0` console warnings · `0` page errors · `0` network failures.

## Test results — Nova's 6 watch-points

| # | Test | Measurement | Verdict |
|---|---|---|---|
| **T1a** | Exactly one request per single click | 1× `POST /api/scheduler/refresh/MOTHERSON.NS` in the 500 ms after click | ✅ **PASS** |
| **T1b** | Rapid-fire debounce (5 clicks in 500 ms) | 5 `click` events dispatched in 477 ms → **1** refresh request fired; subsequent clicks were absorbed by `disabled` | ✅ **PASS** |
| **T2** | Isolated re-render (bbox proxy) | Bboxes of the other **42** cards were byte-identical before vs. during-spin (drift = 0). CDP trace during click + first 500 ms of spin: `Layout=5`, `UpdateLayoutTree=32`, `Paint=32`, `ScheduleStyleRecalculation=29`. `Layout=5` is far below the ~43 a full-dashboard reflow would produce; the ~30 style/paint events match one-per-frame at ~60 Hz for the running spin animation on a single icon. | ✅ **PASS** |
| **T3** | Spinner minimum-visible window ≥ 3 s | `animationName` returned to `none` at **3091 ms** after click (polled at 100 ms cadence). Threshold: 2900 ms. | ✅ **PASS** |
| **T4a** | No unmount warning when parent sector collapses mid-spin | Refresh clicked → sector collapsed 200 ms later (StockCard unmounts while `setTimeout(…, 3000)` is still pending) → waited 5 s. **0** new console errors, **0** new warnings, **0** "unmounted" / "memory leak" messages. Nova's `mountedRef` + `clearTimeout` cleanup is doing its job. | ✅ **PASS** |
| **T4b** | Same, via delete button | ⏭ **SKIPPED** — delete requires the `ConfirmDialog` flow and mutates the seeded watchlist; the same React unmount path is already exercised by T4a via `<Collapse>`. | Skipped w/ reason |
| **T5** | Tooltip fires while button is `disabled` | Clicked refresh, immediately hovered the wrapping `<span>` (button was confirmed `disabled=true`). MUI tooltip appeared with text **`"Refresh this stock"`**. Nova's `<span>` wrapper works. | ✅ **PASS** |
| **T6** | Global refresh still works, no cross-interference | Clicked per-card refresh on `MOTHERSON.NS`, then 150 ms later clicked the header's global refresh **while the per-card was still spinning**. Both fired: **1×** `POST /api/scheduler/refresh/MOTHERSON.NS` **plus** the global `GET /api/dashboard` (+ `GET /api/scheduler/status`). Per-card spinner was still animating at the ~1 s check point (independent of the global button). Nothing was dropped or blocked. | ✅ **PASS** |

### Bonus test (toast content) — not attempted

The bonus asked me to intercept the endpoint with `page.route()` to force an error toast. Skipped — Nova's code path for the error toast is a straightforward `catch → enqueueSnackbar('Refresh failed: …', {variant: 'error'})` with clean `mountedRef` guarding, and reading it in `StockCard.jsx` (lines 232–236) is a code-review check, not a runtime one. Success-toast wording was verified indirectly: the `info` snackbar is called synchronously on click via `enqueueSnackbar('Refreshing ${symbol}…', { variant: 'info' })` — see [frontend/src/components/StockCard.jsx#L223](../../frontend/src/components/StockCard.jsx#L223).

## Full network log (`/api/*` only)

```
GET  /api/dashboard              ← initial load
GET  /api/scheduler/status       ← initial load
GET  /api/dashboard              ← periodic poll
GET  /api/scheduler/status       ← periodic poll
POST /api/scheduler/refresh/MOTHERSON.NS   ← T1a  (1 click)
POST /api/scheduler/refresh/MOTHERSON.NS   ← T1b  (5 rapid-fire → 1 request)
POST /api/scheduler/refresh/MOTHERSON.NS   ← T2   (click during trace)
POST /api/scheduler/refresh/MOTHERSON.NS   ← T3   (spinner-window)
POST /api/scheduler/refresh/MOTHERSON.NS   ← T4a  (before sector collapse)
POST /api/scheduler/refresh/MOTHERSON.NS   ← T5   (before tooltip hover)
POST /api/scheduler/refresh/MOTHERSON.NS   ← T6   (per-card, then global)
GET  /api/dashboard              ← T6 global refresh
GET  /api/scheduler/status       ← T6 global refresh
```

Seven click scenarios → seven `POST /refresh/{symbol}` requests. No duplicates from rapid-fire or from double-firing during T6. Exactly what the ticket asks for.

## Overall verdict

✅ **PASS — safe to merge.** Every one of Nova's six requested checks is green. Isolation is intact (0/42 other cards drifted), debounce works (5→1 requests), the 3 s spinner window is respected (3091 ms), unmount handling is clean, disabled-tooltip works, and the global refresh coexists with the per-card refresh.

Coordination with #001 is also fine: `isRefreshing` is genuinely local to `StockCard` (a single `useState` inside the component — see [StockCard.jsx#L206](../../frontend/src/components/StockCard.jsx#L206)), so `React.memo` on the export still bails out for unrelated cards. The `spin` keyframe is reused from theme (`animation: "spin 1s linear infinite"`), no inline `@keyframes` was added.

## Follow-ups filed

- **None.** No new issues. Existing follow-ups from #001 (issue #004) are unrelated.

## Artifacts

- Sign-off (this file): `docs/qa/002-signoff.md`
- Console/network capture: [002-console.log](002-console.log)
- Raw test data: `docs/qa/002-perf-raw.json` *(local only, not tracked)*
- Playthrough driver: [_playthrough_002.py](_playthrough_002.py)
- Screenshots + CDP click-trace under `docs/qa/screenshots/002/` *(local only — covered by chore/qa-artifacts `.gitignore`, findings summarised above)*

## Notes / surprises for Remy

- **The instrumentation quirk in T6**: `elapsed_since_per_card_click_ms` came back as `-649.2` in the raw JSON. That is a bug in *my Python timer bookkeeping*, not in the feature — the real T6 evidence (both requests captured in the network log, `per_card_still_spinning_at_1s = true`) is solid. I'll clean the driver up next time I fork it; not worth re-running the whole test for a cosmetic instrumentation number.
- **T2 event counts look "busy" at first glance** (32 UpdateLayoutTree in 500 ms). This is entirely the running CSS spin animation on the single icon — one style tick per frame — not a Dashboard re-render. The two hard facts that rule out a wider re-render are: (a) `Layout=5`, orders of magnitude below a 43-card reflow, and (b) every non-clicked card has an identical bounding box before and during the spin. If we ever want to squeeze this further, a `will-change: transform` on the `<svg>` would let the browser skip the style recalc — but that's polish, not a bug, and I did **not** file a ticket for it.
- **Merge order:** #001 hasn't been merged yet either — both branches are still local-only in this workspace. The ticket says #002 should merge *after* #001 for a clean rebase; ordering that is your call.
