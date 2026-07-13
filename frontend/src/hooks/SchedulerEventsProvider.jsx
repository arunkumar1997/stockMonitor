/**
 * SchedulerEventsProvider — the app-wide bridge to GET /api/scheduler/events.
 *
 * One EventSource per browser tab (opened on mount, closed on unmount).
 * Events are folded into a tiny external store; consumers subscribe via
 * the selector hooks in ./useSchedulerEvents.js.
 *
 * The store is intentionally shaped so per-symbol writes only bump the
 * per-symbol entry's reference — every other card's selector snapshot
 * stays reference-equal, so `useSyncExternalStore` bails out with no
 * re-render (preserves the #001 "no cross-card re-render" acceptance
 * signal). See docs/issues/007-scheduler-sse-migration.md.
 */

import React, { useEffect, useState } from "react";
import { SchedulerEventsContext } from "./SchedulerEventsContext";

const SSE_URL = "http://localhost:8000/api/scheduler/events";
const LOG_CAP = 500;

// ── Store factory ─────────────────────────────────────────────────────────────
//
// A minimal external store à la Redux, but hand-rolled so we can enforce
// the reference-preservation invariants above without pulling in a lib.

function createStore() {
  let state = {
    status: null, // whole scheduler.status() blob (or null pre-snapshot)
    lastFetchStatus: {}, // { "SYM.NS": { status, message, ts } }
    logs: [], // newest first, capped at LOG_CAP
    connected: false, // true while the EventSource is open
  };
  const listeners = new Set();

  const emit = () => {
    // Snapshot listeners so a listener removing itself mid-notify doesn't
    // skip its neighbour. Set iteration is safe under insert but not delete.
    for (const l of Array.from(listeners)) l();
  };

  return {
    getState: () => state,
    subscribe(l) {
      listeners.add(l);
      return () => listeners.delete(l);
    },

    // ── Event handlers — each mutates ONLY the slice it needs ────────────────

    applySnapshot(payload) {
      // `payload.status.last_fetch_status` is the authoritative per-symbol
      // map on connect; mirror it into `lastFetchStatus` so per-card
      // selectors have data on first paint.
      const status = payload.status || null;
      state = {
        ...state,
        status,
        lastFetchStatus: (status && status.last_fetch_status) || {},
        logs: Array.isArray(payload.logs) ? payload.logs.slice(0, LOG_CAP) : [],
      };
      emit();
    },

    applyFetchStarted(evt) {
      // Only status.current_symbol / queued change — keep lastFetchStatus
      // reference stable so card selectors don't fire.
      if (!state.status) {
        state = {
          ...state,
          status: { current_symbol: evt.symbol, queued: evt.queued },
        };
      } else {
        state = {
          ...state,
          status: {
            ...state.status,
            current_symbol: evt.symbol,
            queued: evt.queued,
          },
        };
      }
      emit();
    },

    applyFetchFinished(evt) {
      const key = (evt.symbol || "").toUpperCase();
      const entry = {
        status: evt.status,
        message: evt.message,
        ts: evt.ts,
      };
      // Only the finished symbol's entry gets a new reference. Every other
      // key in lastFetchStatus retains its old reference → other cards'
      // selector snapshots are Object.is-equal → no re-render.
      state = {
        ...state,
        lastFetchStatus: { ...state.lastFetchStatus, [key]: entry },
        status: state.status
          ? {
              ...state.status,
              current_symbol: "",
              queued: evt.queued,
              last_fetch_status: {
                ...state.lastFetchStatus,
                [key]: entry,
              },
            }
          : state.status,
      };
      emit();
    },

    applyLog(evt) {
      // Prepend, cap at LOG_CAP. Only useSchedulerLogs subscribers care.
      const nextLogs = [evt, ...state.logs];
      if (nextLogs.length > LOG_CAP) nextLogs.length = LOG_CAP;
      state = { ...state, logs: nextLogs };
      emit();
    },

    setConnected(v) {
      if (state.connected === v) return;
      state = { ...state, connected: v };
      emit();
    },
  };
}

// ── Provider ──────────────────────────────────────────────────────────────────

export function SchedulerEventsProvider({ children }) {
  // One store instance for the whole provider lifetime. `useState` with a
  // lazy initializer gives us a stable value across re-renders (we never
  // call the setter), so the context value never changes → no
  // context-driven re-renders further down the tree.
  const [store] = useState(createStore);

  useEffect(() => {
    const es = new EventSource(SSE_URL);
    let failureCount = 0;

    es.onopen = () => {
      failureCount = 0;
      store.setConnected(true);
    };

    es.onmessage = (msg) => {
      let evt;
      try {
        evt = JSON.parse(msg.data);
      } catch {
        return;
      }
      switch (evt.type) {
        case "status_snapshot":
          store.applySnapshot(evt);
          break;
        case "fetch_started":
          store.applyFetchStarted(evt);
          break;
        case "fetch_finished":
          store.applyFetchFinished(evt);
          break;
        case "log":
          store.applyLog(evt);
          break;
        default:
          // Unknown event type — ignore for forward-compat.
          break;
      }
    };

    es.onerror = () => {
      // Browser auto-reconnects; we just track the connection state and
      // occasionally warn if failures pile up.
      store.setConnected(false);
      failureCount += 1;
      if (failureCount === 5) {
        console.warn(
          "[scheduler-sse] EventSource has failed 5+ times in a row; " +
            "browser is auto-reconnecting.",
        );
      }
    };

    return () => {
      es.close();
      store.setConnected(false);
    };
  }, [store]);

  return (
    <SchedulerEventsContext.Provider value={store}>
      {children}
    </SchedulerEventsContext.Provider>
  );
}
