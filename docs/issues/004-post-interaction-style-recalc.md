# Issue #004 — Residual 60 Hz style-recalc scheduling after opening panels

**Type:** perf-nit
**Severity:** minor (not user-visible; wastes ≈0.5% main-thread when idle after interaction)
**Area:** frontend
**Reporter:** Ivy (QA)
**Triaged by:** Ivy (QA)
**Assignee:** unassigned — deferrable

---

## Symptom

After opening and closing a header panel (Logs / Settings / Trash) or clicking a sector toggle, an *idle* dashboard schedules extra style recalculations that persist for several seconds and, when several interactions are chained, can reach the full 60 Hz frame rate.

Concrete numbers from CDP traces on `fix/ui-lag-header-menu` @ commit `51a2bd1`, seeded DB (43 cards):

| Scenario | 5 s idle trace, `UpdateLayoutTree` count | `ScheduleStyleRecalculation` |
|---|---:|---:|
| Right after page load, no interaction | **0** | **0** |
| After 1 theme toggle | 0 | 0 |
| After cycling theme dark→light→auto→dark | 0 | 0 |
| After opening + Escape-closing Logs panel | 15 (≈3/s) | 15 |
| After opening + Escape-closing Trash panel | 16 (≈3/s) | 16 |
| After chained theme + logs + settings + trash + sector-toggle | **301 (≈60/s)** | **301** |

Total `UpdateLayoutTree` duration in the 60 Hz worst case: ≈26 ms across 5000 ms (~0.5% main thread).

Raw traces attached: [docs/qa/screenshots/001/post-interaction-idle-trace.json](../qa/screenshots/001/post-interaction-idle-trace.json), [docs/qa/screenshots/001/diag-after-logs.json](../qa/screenshots/001/diag-after-logs.json), [docs/qa/screenshots/001/diag-after-trash.json](../qa/screenshots/001/diag-after-trash.json).

## Why this is *not* a #001 regression

Ticket [#001](001-ui-lag-header-menu.md) called for eliminating the 1 Hz whole-tree re-render caused by the countdown. That is confirmed fixed — the clean idle trace (right after load) shows **0** `UpdateLayoutTree` events over 5 s. This new observation only appears **after** UI interaction, and even then the events are cheap (< 0.1 ms each) and never cascade into `Layout` (steady 5 events @ 1 Hz — CountdownBadge only) or extra `Paint` (steady 10 events). No user-visible jank.

## Reproducer

```bash
# Preconditions: DB seeded, backend + frontend running.
# In a headless Chromium via CDP:
1. Load http://localhost:5173 and wait until idle.
2. Click the Logs icon (ArticleIcon), wait 700 ms.
3. Press Escape, wait 2000 ms.
4. Start a CDP Tracing session over
   "devtools.timeline,disabled-by-default-devtools.timeline".
5. Wait 5000 ms.
6. Stop tracing and count events named "UpdateLayoutTree" and
   "ScheduleStyleRecalculation" — expect ≈15 of each (vs 0 in baseline).
```

Automated repro lives in [docs/qa/_diagnose.py](../qa/_diagnose.py).

## Suspected root cause

Not fully investigated, but the correlation is with `MuiDrawer` open/close and `MuiCollapse` transitions. Two plausible sources:

1. A `focus-visible` listener (or MUI `useIsFocusVisible`) left attached after the Drawer's focus-trap tears down, keeping style invalidations scheduled while the last-clicked element retains focus.
2. A short-lived MUI transition (Drawer slide, Collapse) whose cleanup schedules one final microtask that reads a layout property on every subsequent frame for a short period.

Neither is proven — the traces above are the raw evidence. Someone from the frontend team should attach the React DevTools Profiler + Chrome DevTools Performance tab and click through the same sequence.

## Suggested fix

- Reproduce in the Chrome DevTools Performance panel (not just CDP JSON) so the "Initiator" column identifies the exact source of each `ScheduleStyleRecalculation`.
- If it turns out to be a lingering focus/hover state, forcing `blur()` on close or explicitly clearing `document.activeElement` in the Drawer `onClose` handler may resolve it.
- If it's a MUI transition side-effect, upgrading `@mui/material` or wrapping affected content in `contain: layout style` may help.

## Out of scope

- Not blocking #001.
- Not user-visible — do not spend a whole sprint on this. Nice-to-have cleanup once someone is already touching Drawer / Collapse code.

## Branch suggestion

- Branch (when picked up): `perf/idle-style-recalc-after-panels`
- Suggested PR title: `perf(idle): eliminate residual UpdateLayoutTree scheduling after panel close`
