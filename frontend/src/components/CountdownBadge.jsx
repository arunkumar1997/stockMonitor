import React, { useEffect, useRef, useState } from "react";
import Typography from "@mui/material/Typography";

/**
 * Small self-contained countdown display. Owns its own 1Hz tick so that the
 * parent tree does not re-render every second. When `lastUpdated` changes,
 * the countdown resets to `intervalSec`. When the countdown reaches zero,
 * `onExpire` (if provided) is invoked and the countdown resets.
 */
export default function CountdownBadge({ intervalSec, lastUpdated, onExpire }) {
  const [remaining, setRemaining] = useState(intervalSec);

  // Keep the latest onExpire in a ref so the tick effect doesn't need to
  // re-subscribe every time the parent passes a new function reference.
  const onExpireRef = useRef(onExpire);
  useEffect(() => {
    onExpireRef.current = onExpire;
  }, [onExpire]);

  // Reset the visible countdown whenever a fresh update lands.
  useEffect(() => {
    setRemaining(intervalSec);
  }, [lastUpdated, intervalSec]);

  useEffect(() => {
    const tick = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          if (onExpireRef.current) onExpireRef.current();
          return intervalSec;
        }
        return prev - 1;
      });
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
