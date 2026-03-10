import React, { useState } from "react";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import Skeleton from "@mui/material/Skeleton";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import SignalBadge from "./SignalBadge";
import Sparkline from "./Sparkline";
import NewsPanel from "./NewsPanel";

function formatPrice(price, currency) {
  if (!price) return "—";
  const locale = currency === "INR" ? "en-IN" : "en-US";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currency || "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

function DipMeter({ dip }) {
  if (!dip) return null;
  const severityColors = {
    extreme: "#ff5252",
    high: "#ff7043",
    moderate: "#ffa726",
    minor: "#ffcc02",
    none: "#00e676",
  };
  const color = severityColors[dip.severity] || "#90a4ae";
  const pct = Math.min(dip.dip_pct, 25); // cap at 25% for progress bar

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={600}>
          DIP FROM RECENT HIGH
        </Typography>
        <Typography variant="caption" sx={{ color, fontWeight: 700 }}>
          {dip.dip_pct > 0 ? `-${dip.dip_pct}%` : "At High"}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={(pct / 25) * 100}
        sx={{
          "& .MuiLinearProgress-bar": {
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 4,
          },
        }}
      />
      {dip.severity !== "none" && (
        <Typography variant="caption" sx={{ color, mt: 0.3, display: "block" }}>
          {dip.severity.charAt(0).toUpperCase() + dip.severity.slice(1)} dip · High: {formatPrice(dip.recent_high)}
        </Typography>
      )}
    </Box>
  );
}

function ResistanceMeter({ current, resistanceLevels, supportLevels, currency }) {
  if (!resistanceLevels?.length && !supportLevels?.length) return null;
  const nearest = resistanceLevels?.[0];

  let proxPct = 0;
  if (nearest && current > 0) {
    proxPct = Math.min(((nearest - current) / current) * 100, 20);
  }

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={600}>
          RESISTANCE
        </Typography>
        {nearest ? (
          <Typography variant="caption" sx={{ color: "#00b4d8", fontWeight: 700 }}>
            {formatPrice(nearest, currency)} ({proxPct.toFixed(1)}% away)
          </Typography>
        ) : (
          <Typography variant="caption" color="text.secondary">N/A</Typography>
        )}
      </Box>
      <LinearProgress
        variant="determinate"
        value={nearest ? Math.max(0, 100 - (proxPct / 20) * 100) : 0}
        sx={{
          "& .MuiLinearProgress-bar": {
            background: "linear-gradient(90deg, #00b4d888, #00b4d8)",
            borderRadius: 4,
          },
        }}
      />
      {supportLevels?.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.3, display: "block" }}>
          Support: {formatPrice(supportLevels[0], currency)}
        </Typography>
      )}
    </Box>
  );
}

export default function StockCard({ stock, onRemove }) {
  const [loading, setLoading] = useState(false);

  if (!stock) return null;

  const { signal, dip, resistance_levels, support_levels,
    current_price, price_change_pct, price_change,
    sparkline, rsi, moving_averages, news, currency,
    fifty_two_week_high, fifty_two_week_low, name, symbol, error } = stock;

  const isPositive = price_change_pct >= 0;
  const PriceIcon = isPositive ? TrendingUpIcon : TrendingDownIcon;
  const priceColor = isPositive ? "#00e676" : "#ff5252";

  if (error) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" color="text.secondary">{symbol}</Typography>
          <Typography variant="caption" color="error">
            Failed to load: {error}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent sx={{ p: 2.5 }}>
        {/* Header */}
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1.5 }}>
          <Box>
            <Typography variant="h6" fontWeight={800} sx={{ lineHeight: 1.1 }}>
              {symbol}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {name}
            </Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.5 }}>
            <SignalBadge signal={signal?.signal} confidence={signal?.confidence} size="small" />
            <IconButton size="small" onClick={() => onRemove(symbol)} sx={{ color: "error.main", opacity: 0.5, "&:hover": { opacity: 1 } }}>
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>

        {/* Price */}
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 0.5 }}>
          <Typography variant="h5" fontWeight={800} sx={{ letterSpacing: "-0.5px" }}>
            {formatPrice(current_price, currency)}
          </Typography>
          <Chip
            icon={<PriceIcon sx={{ fontSize: "14px !important" }} />}
            label={`${isPositive ? "+" : ""}${price_change_pct?.toFixed(2)}%`}
            size="small"
            sx={{
              background: isPositive ? "rgba(0,230,118,0.15)" : "rgba(255,82,82,0.15)",
              color: priceColor,
              border: `1px solid ${priceColor}40`,
              fontWeight: 700,
              fontSize: "0.75rem",
              height: 22,
            }}
          />
        </Box>

        {/* Sparkline */}
        <Box sx={{ mx: -1, mb: 1 }}>
          <Sparkline data={sparkline} positive={isPositive} currency={currency} />
        </Box>

        <Divider sx={{ borderColor: "rgba(255,255,255,0.06)", mb: 1.5 }} />

        {/* Dip Meter */}
        <Box sx={{ mb: 1.5 }}>
          <DipMeter dip={dip} currency={currency} />
        </Box>

        {/* Resistance Meter */}
        <Box sx={{ mb: 1.5 }}>
          <ResistanceMeter
            current={current_price}
            resistanceLevels={resistance_levels}
            supportLevels={support_levels}
            currency={currency}
          />
        </Box>

        {/* Stats Row */}
        <Box sx={{ display: "flex", gap: 1, mb: 1.5, flexWrap: "wrap" }}>
          {rsi != null && (
            <Tooltip title="Relative Strength Index: <30 oversold, >70 overbought">
              <Chip
                icon={<ShowChartIcon sx={{ fontSize: "14px !important" }} />}
                label={`RSI ${rsi}`}
                size="small"
                sx={{
                  background: rsi < 30 ? "rgba(0,230,118,0.12)" : rsi > 70 ? "rgba(255,82,82,0.12)" : "rgba(255,255,255,0.06)",
                  color: rsi < 30 ? "#00e676" : rsi > 70 ? "#ff5252" : "text.secondary",
                  border: "1px solid rgba(255,255,255,0.08)",
                  fontWeight: 700,
                  fontSize: "0.72rem",
                  height: 20,
                }}
              />
            </Tooltip>
          )}
          {moving_averages?.ma20 && (
            <Tooltip title="20-day Moving Average">
              <Chip
                label={`MA20: ${formatPrice(moving_averages.ma20, currency)}`}
                size="small"
                sx={{
                  background: "rgba(255,255,255,0.04)",
                  color: "text.secondary",
                  border: "1px solid rgba(255,255,255,0.08)",
                  fontWeight: 600,
                  fontSize: "0.72rem",
                  height: 20,
                }}
              />
            </Tooltip>
          )}
          {fifty_two_week_high > 0 && (
            <Tooltip title="52-week range">
              <Chip
                label={`52w: ${formatPrice(fifty_two_week_low, currency)} – ${formatPrice(fifty_two_week_high, currency)}`}
                size="small"
                sx={{
                  background: "rgba(255,255,255,0.04)",
                  color: "text.secondary",
                  border: "1px solid rgba(255,255,255,0.08)",
                  fontSize: "0.68rem",
                  fontWeight: 600,
                  height: 20,
                }}
              />
            </Tooltip>
          )}
        </Box>

        {/* Signal Reasons */}
        {signal?.reasons?.length > 0 && (
          <Box sx={{ mb: 1.5, p: 1, borderRadius: 2, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>
              SIGNAL RATIONALE
            </Typography>
            {signal.reasons.map((r, i) => (
              <Typography key={i} variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.6, pl: 1, "&::before": { content: '"· "' } }}>
                {r}
              </Typography>
            ))}
          </Box>
        )}

        <Divider sx={{ borderColor: "rgba(255,255,255,0.06)", mb: 1 }} />

        {/* News Panel */}
        <NewsPanel news={news} />
      </CardContent>
    </Card>
  );
}
