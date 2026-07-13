# Issue #001 — UI is laggy, especially the header action menu

**Type:** bug
**Severity:** major (perceived performance / UX)
**Area:** frontend
**Reporter:** CEO
**Triaged by:** Remy (Producer)
**Assignee:** Nova (Frontend)

---

## Symptom

The whole UI feels laggy. Especially noticeable on the top-right header action menu (refresh / trash / logs / settings / theme toggle icons) — hover and click feedback stutters, tooltips feel delayed, the refresh spin animation janks.

## Root cause (triage findings)

The `Dashboard` re-renders **the entire tree once per second** because of the countdown timer, and none of the children are memoized. Combined with expensive MUI + Recharts subtrees, this saturates the main thread.

Evidence in [frontend/src/components/Dashboard.jsx](frontend/src/components/Dashboard.jsx):

1. **1 Hz forced re-render of the whole app** — [Dashboard.jsx#L182-L188](frontend/src/components/Dashboard.jsx#L182-L188)
   ```js
   const tick = setInterval(() => {
     setCountdown((prev) => { ... });
   }, 1000);
   ```
   `countdown` lives in `Dashboard` state, so every tick re-renders `Dashboard` → every `SectorSection` → every `StockCard` → every `Sparkline` (Recharts `ResponsiveContainer` + `AreaChart`, which is not cheap to reconcile).

2. **No memoization anywhere.** `grep` confirms `React.memo` is used 0 times across `frontend/src/`. `StockCard`, `SectorSection`, `Sparkline`, `NewsPanel`, `SignalBadge` all re-render on every parent render.

3. **`filteredStocks` and `grouped` recomputed every render** — [Dashboard.jsx#L211-L225](frontend/src/components/Dashboard.jsx#L211-L225). Not wrapped in `useMemo`, so `.filter().reduce()` over all stocks runs every countdown tick.

4. **Inline `@keyframes` inside `sx` on the header buttons** — [Dashboard.jsx#L266-L272](frontend/src/components/Dashboard.jsx#L266-L272) and the "fetching" chip [Dashboard.jsx#L246-L256](frontend/src/components/Dashboard.jsx#L246-L256).
   The `sx` object is a fresh literal every render → MUI re-hashes it and re-injects the `@keyframes spin` / `@keyframes pulse` stylesheet rules on every 1 s tick. This is a documented MUI perf anti-pattern and directly affects the exact menu the user pointed at.

5. **`SectorSection` re-computes signal-count reduce on every render** — [Dashboard.jsx#L106-L120](frontend/src/components/Dashboard.jsx#L106-L120). Fine per-render, expensive at 1 Hz × N sectors.

6. **`Sparkline` uses `ResponsiveContainer`** — [frontend/src/components/Sparkline.jsx](frontend/src/components/Sparkline.jsx). This component installs a `ResizeObserver` per instance and re-measures on every re-render cycle. With 20–50 cards this dominates the frame budget.

Net effect: every second, React reconciles the whole dashboard + Recharts re-lays out every sparkline + MUI re-injects animation stylesheets → main-thread stalls make the header icons feel unresponsive.

## Fix plan (for Nova)

Do these in order, small commits, measure with the browser Performance panel between each.

### Must-fix (should eliminate the lag)

- [ ] **Isolate the countdown.** Extract the countdown display into its own small `<CountdownBadge />` component that owns its own `useState` + `setInterval`. Remove `countdown` state from `Dashboard`. Result: the header/sector tree stops re-rendering every second.
- [ ] **Move the auto-refresh trigger out of the countdown.** Use a separate `setInterval` of `REFRESH_INTERVAL * 1000` ms (or a `setTimeout` chain) that calls `fetchDashboard(true)` directly — do not couple it to the 1 Hz UI tick.
- [ ] **Memoize the header action bar.** Extract the action-button cluster (refresh / trash / logs / settings / theme) into `<HeaderActions />` wrapped in `React.memo`. Pass stable callbacks via `useCallback`.
- [ ] **Move `@keyframes` out of inline `sx`.** Define `spin` and `pulse` once — either in `theme.components` global styles, in `index.css`, or via `styled()` — so MUI doesn't re-inject them every render.
- [ ] **`useMemo` for `filteredStocks`, `grouped`, and `signalCounts`** in `Dashboard`.
- [ ] **`React.memo` `StockCard`, `SectorSection`, `Sparkline`, `SignalBadge`.** Ensure `onRemove` / `onToggleCollapse` are stable via `useCallback` so memo actually works.

### Should-fix

- [ ] Give `Sparkline` a fixed width + height (drop `ResponsiveContainer`) or wrap it in `React.memo` with a custom `areEqual` that only compares the `data` array reference.
- [ ] Set `isAnimationActive={false}` is already set — good. Verify no other Recharts child animates.
- [ ] Audit `LogsPanel` — [LogsPanel.jsx#L107](frontend/src/components/LogsPanel.jsx#L107) polls every 2 s. Confirm it only runs while the panel is open.

### Nice-to-have

- [ ] Add a small perf smoke test: render 30 mocked stocks, assert `<StockCard>` render count stays flat across a 5 s window (react-testing-library `render` + a render counter).

## Success criteria

- Hover/click on any header icon responds within one frame (visually snappy).
- Chrome DevTools Performance recording of a 5 s idle window shows `Dashboard` rendering **at most 1×** (from data refresh), not every second.
- React DevTools Profiler: `StockCard` render count during a 10 s idle window = 0 (excluding the initial mount and any real data refresh).
- No visual regressions: countdown still ticks, refresh spin still animates, "fetching X" chip still pulses.

## Out of scope

- Backend changes.
- Redesign of the header layout.
- Switching charting library.

## Branch / PR

- Branch: `fix/ui-lag-header-menu`
- PR title: `fix: eliminate 1Hz full-tree rerender causing header menu lag (Fixes #001)`
- Commit style: one commit per checkbox above so it's easy to bisect if something regresses.
