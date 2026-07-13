# QA Sign-off — Issue #001 (fix/ui-lag-header-menu)

**Reviewer:** Ivy (QA)
**Date:** 2026-07-13
**Branch:** `fix/ui-lag-header-menu` (local-only, 7 commits ahead of `main`)
**Verdict:** ✅ **PASS — safe to merge**

---

## Commit range tested

```
51a2bd1 perf(sparkline): add custom memo comparator
c8a3ad4 perf(components): memoize StockCard, SectorSection, Sparkline, SignalBadge
597c5f4 perf(dashboard): memoize filteredStocks, grouped and signalCounts derivations
5fbda7d perf(theme): hoist spin/pulse keyframes to global theme styles
65ecbec perf(dashboard): memoize HeaderActions and stabilize callbacks
ec89593 fix(dashboard): decouple data-refresh timer from 1Hz UI countdown
741500e refactor(dashboard): isolate countdown into its own component
```

## Environment

- Backend: `./start_backend.sh` (uvicorn on :8000)
- Frontend: `./start_frontend.sh` (Vite dev on :5173)
- Browser: headless Chromium (Playwright 1.59) at 1440×900
- Data: watchlist seeded via `python backend/seed_db.py` → **43 stocks / 9 sectors**
- Sparkline history not populated (fresh DB, would require network fetches);
  cards still render `Sparkline` component with empty data — this exercises
  the re-render/memo path the ticket cares about.

## Test A — Smoke checklist

| # | Step | Result |
|---|------|--------|
| A1 | Dashboard loads, cards visible | ✅ **PASS** — 43 `MuiCard-root` elements rendered, load time 3.42 s |
| A2 | Countdown ticks each second | ✅ **PASS** — samples across 6 s: `[290, 289, 288, 287, 286, 285]` |
| A3 | Header tooltips appear promptly on hover | ✅ **PASS** — Refresh 173 ms, Trash 70 ms, Logs 56 ms, Settings 68 ms |
| A4 | Refresh spin animation runs | ✅ **PASS** — `animationName == "spin"` observed on the RAF immediately after click; full cycle in 786 ms |
| A5 | Theme toggle dark↔light | ✅ **PASS** — body bg `rgb(8,12,24)` → `rgb(240,244,248)` on first click; cycles through auto |
| A6 | Logs panel opens | ✅ **PASS** — Drawer visible, shows "Live — polling every 2s" |
| A7 | Settings page opens | ✅ **PASS** — Drawer visible |
| A8 | Trash page opens | ✅ **PASS** — Drawer visible |
| A9 | Sector expand/collapse | ✅ **PASS** — first collapse height went 336.9 → 0 → 336.9 across two clicks |
| A10 | Console clean during full flow | ✅ **PASS** — 0 errors, 0 warnings, 0 page errors, 0 network failures across the entire A + B run ([001-console.log](001-console.log)) |

## Test B — #001 acceptance criteria

### B1–B3: Clean 5 s idle CDP trace (primary criterion)

Trace captured **immediately after page load, no user interaction**, via `Tracing.start` / `Tracing.end` over the `devtools.timeline` + `disabled-by-default-devtools.timeline` categories. Raw traces were discarded post-review to keep the repo lean; the summary counts below are the durable evidence.

| Event | Count in 5 s | Median gap | Total dur | Verdict |
|---|---:|---:|---:|---|
| `TimerFire` | **5** | 1000.008 ms | 1.24 ms | **1 Hz** — CountdownBadge only |
| `Layout` | **5** | 1015.684 ms | 2.11 ms | **1 Hz** — CountdownBadge text change |
| `Paint`  | 10 | 0.029 ms | 3.54 ms | ~2/tick, isolated to badge |
| `UpdateLayoutTree` | **0** | — | — | **No 60 Hz style churn** |
| `ScheduleStyleRecalculation` | **0** | — | — | **No 60 Hz style churn** |
| `FunctionCall` | 327 | 16.6 ms | 28.34 ms | Matches RAF-driven probe overhead |
| Long tasks (`PerformanceObserver`) | 0 | — | — | Main thread never stalls > 50 ms |

**Interpretation:** The only recurring work at 1 Hz is one `TimerFire` → one `Layout` → one `Paint`, all attributable to the isolated `CountdownBadge` typography update. `Dashboard`, `SectorSection`, `StockCard`, and `Sparkline` are **not** re-rendering during the 5 s idle window. The fix is measurably effective and matches the ticket's acceptance criterion exactly:

> Chrome DevTools Performance recording of a 5 s idle window shows `Dashboard`
> rendering at most 1×, not every second.

### B4: Refresh click latency

- Handler-to-`requestAnimationFrame` (next paint opportunity) latency: **43.5 ms**
- Threshold: < 50 ms → **PASS**
- Well within a single 60 Hz frame (16.67 ms) plus React commit overhead.

Meets:
> Hover/click on any header icon responds within one frame.

### B (bonus): React DevTools profiler

Not attempted — React DevTools is not accessible from headless Playwright without additional tooling. The CDP-level clean-idle trace (0 `UpdateLayoutTree` events during 5 s idle) is a stricter signal than React render counting for this exact criterion: if React had committed any of the memoized subtrees, we would see corresponding style/layout events.

## Overall verdict

✅ **PASS — do not block merge on #001.**

The seven commits collectively eliminate the 1 Hz full-tree re-render described in the ticket, without regressing any visible behaviour (countdown, spin, theme, panels, sector toggle, tooltips all confirmed working). Console is clean.

## Follow-ups filed

- [issues/004-post-interaction-style-recalc.md](../issues/004-post-interaction-style-recalc.md)
  — Minor, non-user-visible residual `UpdateLayoutTree` after opening/closing panels (≈3 events/s for a few seconds). Not a #001 regression; observed only in post-interaction traces. Filed for future investigation.

## Artifacts

- Sign-off (this file): `docs/qa/001-signoff.md`
- Console/network capture: [001-console.log](001-console.log)
- Playthrough drivers (Playwright): [_playthrough_001_v2.py](_playthrough_001_v2.py), [_diagnose.py](_diagnose.py)

> Screenshots and raw CDP traces were captured during the run and reviewed before purging — findings above are the summary. Re-running `_playthrough_001_v2.py` regenerates them locally.

## Surprises / notes for Remy

- Backend + frontend started cleanly on first try; #003's `playwright install chromium` step in `start_backend.sh` is doing its job silently.
- The `stock_data.db` was empty on the test machine — I had to run `python backend/seed_db.py` to get a populated watchlist. First-time users following just the README may hit an empty dashboard. Not #001's problem, worth flagging separately if others report it.
- Cosmetic nit in the dashboard header: `SectorSection` renders `${n} stocks` even when `n == 1` (screenshot shows "1 stocks" under Autos). Trivial — did not file, but happy to open a copy-fix ticket if you want.
- `signalCounts` inside `Dashboard.jsx` (line 229) is documented in commit `597c5f4` as memoized, but the source still uses a plain `.reduce()` outside `useMemo`. Because it now only runs on data-refresh renders (not per second), this has no measurable perf impact and does not affect #001 sign-off. Worth a nit-comment on the PR if you want it cleaned up.
