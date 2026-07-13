import React, { useEffect, useState } from "react";
import Typography from "@mui/material/Typography";

/**
 * Small self-contained countdown display. Owns its own 1Hz tick so that the
 * parent tree does not re-render every second. When `lastUpdated` changes,
 * the countdown resets to `intervalSec`. When the countdown hits zero it
 * wraps back to `intervalSec`; the actual data refresh is driven separately
 * by the parent.
 */
export default function CountdownBadge({ intervalSec, lastUpdated }) {
  const [remaining, setRemaining] = useState(intervalSec);

  // Reset the visible countdown whenever a fresh update lands.
  useEffect(() => {
    setRemaining(intervalSec);
  }, [lastUpdated, intervalSec]);

  useEffect(() => {
    const tick = setInterval(() => {
      setRemaining((prev) => (prev <= 1 ? intervalSec : prev - 1));
    }, 1000);
    return () => clearInterval(tick);
  }, [intervalSec]);

  if (!lastUpdated) return null;

  return (
    <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
      Updated {lastUpdated.toLocaleTimeString()} · {remaining}s
    </Typography>
  );
}
