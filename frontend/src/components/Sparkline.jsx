import React from "react";
import {
  AreaChart,
  Area,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";

function Sparkline({ data = [], positive = true, currency = "USD" }) {
  if (!data || data.length === 0) return null;

  const chartData = data.map((v, i) => ({ i, v }));
  const color = positive ? "#00e676" : "#ff5252";

  return (
    <ResponsiveContainer width="100%" height={70}>
      <AreaChart data={chartData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`spark-${positive}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis domain={["auto", "auto"]} hide />
        <Tooltip
          content={({ payload }) => {
            if (!payload?.length) return null;
            return (
              <div style={{
                background: "rgba(10,14,26,0.9)",
                border: `1px solid ${color}40`,
                borderRadius: 8,
                padding: "4px 10px",
                fontSize: 12,
                color,
              }}>
                {payload[0].value?.toFixed(2)}
              </div>
            );
          }}
        />
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={2}
          fill={`url(#spark-${positive})`}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// Custom comparator: sparkline is expensive (ResizeObserver + full chart
// re-layout). Bail out unless the data actually changed. We keep it cheap by
// only comparing length + first + last data points — good enough given the
// upstream data is a fresh array on each refresh but stable between refreshes.
function areEqual(prev, next) {
  if (prev.positive !== next.positive) return false;
  if (prev.currency !== next.currency) return false;
  const a = prev.data;
  const b = next.data;
  if (a === b) return true;
  if (!a || !b) return false;
  if (a.length !== b.length) return false;
  if (a.length === 0) return true;
  return a[0] === b[0] && a[a.length - 1] === b[b.length - 1];
}

export default React.memo(Sparkline, areEqual);

