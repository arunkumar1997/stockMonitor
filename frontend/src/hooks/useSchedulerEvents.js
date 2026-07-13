/**
 * Selector hooks over the SchedulerEventsProvider store.
 *
 * Each hook uses `useSyncExternalStore` with a narrow snapshot function
 * so subscribers only re-render when THEIR slice changes reference. In
 * particular, `useLastFetchStatus(symbol)` for card X does NOT re-render
 * when card Y finishes fetching — the provider only mutates the entry
 * for the finished symbol, leaving every other reference intact.
 *
 * See docs/issues/007-scheduler-sse-migration.md for the acceptance
 * signal ("idle 5s CDP trace shows 0 renders on cards not involved in
 * any fetch"), and #001 for the original render-budget contract.
 */

import { useContext, useSyncExternalStore } from "react";
import { SchedulerEventsContext } from "./SchedulerEventsContext";

function useStore() {
    const store = useContext(SchedulerEventsContext);
    if (!store) {
        throw new Error(
            "useSchedulerEvents hooks must be used inside a <SchedulerEventsProvider>."
        );
    }
    return store;
}

/**
 * Whole scheduler.status() object (or null before the first snapshot).
 * Consumers: Dashboard header chip.
 *
 * NOTE: `status` changes on status_snapshot, fetch_started, and
 * fetch_finished — NOT on log events. So log traffic does not re-render
 * Dashboard.
 */
export function useSchedulerStatus() {
    const store = useStore();
    return useSyncExternalStore(
        store.subscribe,
        () => store.getState().status
    );
}

/**
 * The per-symbol last-fetch outcome for `symbol` (or null if none yet).
 * Consumers: StockCard (one instance per card, keyed by its own symbol).
 *
 * Because the store only replaces the entry for the finished symbol
 * (and preserves every other key's reference), this hook is `Object.is`
 * stable for cards not involved in the current fetch.
 */
export function useLastFetchStatus(symbol) {
    const store = useStore();
    const key = (symbol || "").toUpperCase();
    return useSyncExternalStore(
        store.subscribe,
        () => store.getState().lastFetchStatus[key] || null
    );
}

/**
 * Full logs buffer (newest first, capped at 500). Consumers: LogsPanel.
 * Re-renders on every `log` event — acceptable since it's a drawer that's
 * only rendered while open.
 */
export function useSchedulerLogs() {
    const store = useStore();
    return useSyncExternalStore(
        store.subscribe,
        () => store.getState().logs
    );
}

/**
 * True while the EventSource is open. Exposed for future UI indicators;
 * currently no consumer.
 */
export function useSchedulerConnected() {
    const store = useStore();
    return useSyncExternalStore(
        store.subscribe,
        () => store.getState().connected
    );
}

// Re-export the provider from a single import location for consumer convenience.
export { SchedulerEventsProvider } from "./SchedulerEventsProvider";
