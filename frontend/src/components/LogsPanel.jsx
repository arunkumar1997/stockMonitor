import React, { useState, useEffect, useRef, useMemo } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import CloseIcon from "@mui/icons-material/Close";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { getLogs } from "../api";
import { useSchedulerLogs } from "../hooks/useSchedulerEvents";

// ── Styling helpers ───────────────────────────────────────────────────────────

const LEVEL_STYLES = {
  SUCCESS: { color: "#00e676", bg: "rgba(0,230,118,0.08)", icon: "✓" },
  ERROR:   { color: "#ff5252", bg: "rgba(255,82,82,0.08)",  icon: "✗" },
  WARN:    { color: "#ffa726", bg: "rgba(255,167,38,0.08)", icon: "⚠" },
  INFO:    { color: "#64b5f6", bg: "transparent",           icon: "ℹ" },
};

function LogRow({ entry }) {
  const st = LEVEL_STYLES[entry.level] || LEVEL_STYLES.INFO;
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 1,
        py: 0.6,
        px: 1,
        borderRadius: 1,
        background: st.bg,
        borderLeft: `2px solid ${entry.level === "INFO" ? "transparent" : st.color}`,
        mb: 0.25,
        "&:hover": { background: "rgba(255,255,255,0.04)" },
      }}
    >
      {/* Icon */}
      <Typography sx={{ color: st.color, fontSize: "0.75rem", fontWeight: 800, minWidth: 14, mt: 0.1 }}>
        {st.icon}
      </Typography>

      {/* Timestamp */}
      <Typography
        component="span"
        sx={{ color: "text.disabled", fontSize: "0.65rem", fontFamily: "monospace", flexShrink: 0, mt: 0.1 }}
      >
        {entry.ts.slice(11)}   {/* HH:MM:SS */}
      </Typography>

      {/* Symbol chip */}
      {entry.symbol && (
        <Chip
          label={entry.symbol}
          size="small"
          sx={{
            height: 16, fontSize: "0.58rem", fontWeight: 800, flexShrink: 0,
            fontFamily: "monospace",
            background: "rgba(255,255,255,0.08)",
            color: "text.secondary",
            "& .MuiChip-label": { px: 0.75 },
          }}
        />
      )}

      {/* Message */}
      <Typography
        sx={{
          color: st.color === "#64b5f6" ? "text.secondary" : st.color,
          fontSize: "0.72rem",
          lineHeight: 1.5,
          wordBreak: "break-word",
          flex: 1,
        }}
      >
        {entry.message}
      </Typography>
    </Box>
  );
}

export default function LogsPanel({ open, onClose }) {
  // Live log stream from the SSE provider. Newest-first, capped at 500.
  const liveLogs = useSchedulerLogs();

  // One-shot backfill: the provider's initial status_snapshot carries only
  // the last 50 log entries. If the panel is opened right after page load
  // (before any live events have arrived) it looked near-empty. Pull the
  // fuller /api/logs?limit=200 once, and merge with anything the live feed
  // has picked up. After that we're pure push.
  const [backfill, setBackfill] = useState([]);
  const backfilledRef = useRef(false);
  useEffect(() => {
    if (!open || backfilledRef.current) return;
    backfilledRef.current = true;
    (async () => {
      try {
        const data = await getLogs(200);
        setBackfill(data);
      } catch {
        /* silently ignore — SSE stream will fill in as new events arrive */
      }
    })();
  }, [open]);

  // Merge live + backfill, dedup by id, newest first, cap at 500.
  const mergedLogs = useMemo(() => {
    if (backfill.length === 0) return liveLogs;
    const seen = new Set(liveLogs.map((l) => l.id));
    const merged = [...liveLogs, ...backfill.filter((d) => !seen.has(d.id))];
    merged.sort((a, b) => b.id - a.id);
    if (merged.length > 500) merged.length = 500;
    return merged;
  }, [liveLogs, backfill]);

  // "Clear display" (doesn't delete from server). Records the current
  // max id as a floor; only entries with id > floor are shown thereafter,
  // so newly-arriving live entries still appear.
  const [clearFloorId, setClearFloorId] = useState(0);
  const visibleLogs = clearFloorId
    ? mergedLogs.filter((l) => l.id > clearFloorId)
    : mergedLogs;

  // Pause: freeze the displayed snapshot so it doesn't scroll away while
  // reading. Snapshot the currently-visible list at the moment pause
  // flips on; drop the snapshot on resume.
  const [paused, setPaused] = useState(false);
  const [frozenLogs, setFrozenLogs] = useState(null);
  useEffect(() => {
    if (paused) setFrozenLogs(visibleLogs);
    else setFrozenLogs(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused]);
  const logs = paused && frozenLogs ? frozenLogs : visibleLogs;

  const [autoScroll, setAutoScroll] = useState(true);
  const [filter,     setFilter]     = useState("ALL");  // ALL | SUCCESS | ERROR | WARN | INFO
  const bottomRef = useRef(null);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current && !paused) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll, paused]);

  const filtered = filter === "ALL" ? logs : logs.filter((l) => l.level === filter);

  const levelCounts = {
    SUCCESS: logs.filter((l) => l.level === "SUCCESS").length,
    ERROR:   logs.filter((l) => l.level === "ERROR").length,
    WARN:    logs.filter((l) => l.level === "WARN").length,
    INFO:    logs.filter((l) => l.level === "INFO").length,
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: "100%", sm: 520 },
          background: (t) => t.palette.mode === "dark"
            ? "linear-gradient(180deg, #0d1117 0%, #111827 100%)"
            : "linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%)",
          display: "flex",
          flexDirection: "column",
        },
      }}
    >
      {/* Header */}
      <Box sx={{
        px: 2.5, py: 2,
        borderBottom: "1px solid",
        borderColor: "divider",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexShrink: 0,
      }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Typography variant="h6" fontWeight={800}>📋 Refresh Logs</Typography>
          <Chip
            label={`${logs.length} entries`}
            size="small"
            sx={{ height: 20, fontSize: "0.65rem", background: "rgba(255,255,255,0.06)" }}
          />
          {levelCounts.ERROR > 0 && (
            <Chip label={`${levelCounts.ERROR} errors`} size="small"
              sx={{ height: 20, fontSize: "0.65rem", background: "rgba(255,82,82,0.15)", color: "#ff5252" }} />
          )}
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Tooltip title={paused ? "Resume live updates" : "Pause live updates"}>
            <IconButton size="small" onClick={() => setPaused((p) => !p)} sx={{ color: paused ? "#ffa726" : "text.secondary" }}>
              {paused ? <PlayArrowIcon fontSize="small" /> : <PauseIcon fontSize="small" />}
            </IconButton>
          </Tooltip>
          <Tooltip title="Clear display (doesn't delete from server)">
            <IconButton
              size="small"
              onClick={() => setClearFloorId(mergedLogs[0]?.id || 0)}
              sx={{ color: "text.secondary" }}
            >
              <DeleteSweepIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>

      {/* Filter bar */}
      <Box sx={{
        px: 2, py: 1,
        borderBottom: "1px solid",
        borderColor: "divider",
        display: "flex",
        gap: 0.75,
        flexWrap: "wrap",
        alignItems: "center",
        flexShrink: 0,
      }}>
        {["ALL", "SUCCESS", "ERROR", "WARN", "INFO"].map((lvl) => {
          const st = LEVEL_STYLES[lvl] || { color: "text.secondary" };
          const cnt = lvl === "ALL" ? logs.length : levelCounts[lvl];
          return (
            <Chip
              key={lvl}
              label={`${lvl} ${cnt}`}
              size="small"
              onClick={() => setFilter(lvl)}
              sx={{
                height: 22, fontSize: "0.65rem", fontWeight: filter === lvl ? 800 : 500, cursor: "pointer",
                background: filter === lvl ? (st.bg || "rgba(255,255,255,0.12)") : "rgba(255,255,255,0.04)",
                color: filter === lvl ? (st.color || "text.primary") : "text.secondary",
                border: `1px solid ${filter === lvl ? (st.color || "rgba(255,255,255,0.3)") : "transparent"}`,
              }}
            />
          );
        })}
        <Box sx={{ ml: "auto" }}>
          <FormControlLabel
            control={
              <Switch checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} size="small" />
            }
            label={<Typography variant="caption" color="text.secondary">Auto-scroll</Typography>}
            labelPlacement="start"
            sx={{ mr: 0, gap: 0.5 }}
          />
        </Box>
      </Box>

      {/* Log entries */}
      <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
        {filtered.length === 0 ? (
          <Box sx={{ textAlign: "center", mt: 6, color: "text.disabled" }}>
            <Typography sx={{ fontSize: "2rem", mb: 1 }}>📋</Typography>
            <Typography variant="body2">
              {logs.length === 0
                ? "No logs yet — trigger a manual refresh to see activity"
                : `No ${filter} entries`}
            </Typography>
          </Box>
        ) : (
          // Reverse to show oldest at top → newest at bottom (like a terminal)
          [...filtered].reverse().map((entry) => (
            <LogRow key={entry.id} entry={entry} />
          ))
        )}
        <div ref={bottomRef} />
      </Box>

      {/* Footer status */}
      <Box sx={{
        px: 2, py: 1,
        borderTop: "1px solid",
        borderColor: "divider",
        display: "flex",
        alignItems: "center",
        gap: 1,
        flexShrink: 0,
      }}>
        <Box sx={{
          width: 7, height: 7, borderRadius: "50%",
          background: paused ? "#ffa726" : "#00e676",
          boxShadow: paused ? "0 0 6px #ffa726" : "0 0 6px #00e676",
          animation: paused ? "none" : "pulse 2s infinite",
          "@keyframes pulse": {
            "0%, 100%": { opacity: 1 },
            "50%": { opacity: 0.4 },
          },
        }} />
        <Typography variant="caption" color="text.secondary">
          {paused ? "Paused" : "Live \u2014 push over SSE"}
        </Typography>
        {filtered.length < logs.length && (
          <Typography variant="caption" color="text.disabled" sx={{ ml: "auto" }}>
            Showing {filtered.length} of {logs.length}
          </Typography>
        )}
      </Box>
    </Drawer>
  );
}
