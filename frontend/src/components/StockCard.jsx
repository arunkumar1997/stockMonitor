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
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import SignalBadge from "./SignalBadge";
import Sparkline from "./Sparkline";
import NewsPanel from "./NewsPanel";
import ConfirmDialog from "./ConfirmDialog";

// ── Fundamental helpers ───────────────────────────────────────────────────────

const VAL_COLORS = {
  UNDERVALUED: { bg: "rgba(0,230,118,0.12)", text: "#00e676", border: "rgba(0,230,118,0.3)" },
  FAIR:        { bg: "rgba(0,180,216,0.10)", text: "#00b4d8", border: "rgba(0,180,216,0.3)" },
  OVERVALUED:  { bg: "rgba(255,160,0,0.12)", text: "#ffa000", border: "rgba(255,160,0,0.3)" },
  STRETCHED:   { bg: "rgba(255,82,82,0.12)",  text: "#ff5252", border: "rgba(255,82,82,0.3)" },
  UNKNOWN:     { bg: "rgba(255,255,255,0.05)", text: "#90a4ae", border: "rgba(255,255,255,0.1)" },
};

function fmt(val, suffix = "", decimals = 1) {
  if (val === null || val === undefined) return "—";
  return `${val.toFixed(decimals)}${suffix}`;
}
function fmtPct(val) { if (val === null || val === undefined) return "—"; return `${(val * 100).toFixed(1)}%`; }
function fmtCr(val, currency) {
  if (val === null || val === undefined) return "—";
  const abs = Math.abs(val);
  const sign = val < 0 ? "-" : "+";
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e7) return `${sign}${(abs / 1e7).toFixed(0)}Cr`;
  return `${sign}${(abs / 1e5).toFixed(0)}L`;
}

function FundamentalPanel({ fundamentals, valuation }) {
  if (!fundamentals || Object.keys(fundamentals).length === 0) return null;
  const status = valuation?.status || "UNKNOWN";
  const c = VAL_COLORS[status] || VAL_COLORS.UNKNOWN;
  const score = valuation?.score;

  const metrics = [
    { label: "P/E",      val: fmt(fundamentals.trailing_pe, "x"),      tip: "Trailing Price-to-Earnings" },
    { label: "Fwd P/E",  val: fmt(fundamentals.forward_pe, "x"),       tip: "Forward Price-to-Earnings" },
    { label: "PEG",      val: fmt(fundamentals.peg_ratio, "", 2),      tip: "PEG Ratio (<1 = growth at discount)" },
    { label: "EV/EBITDA",val: fmt(fundamentals.ev_to_ebitda, "x"),     tip: "Enterprise Value / EBITDA" },
    { label: "P/B",      val: fmt(fundamentals.price_to_book, "x"),    tip: "Price-to-Book Ratio" },
    { label: "D/E",      val: fmt(fundamentals.debt_to_equity, "", 2), tip: "Debt-to-Equity Ratio" },
    { label: "FCF",      val: fmtCr(fundamentals.free_cashflow),       tip: "Free Cash Flow" },
    { label: "Margin",   val: fmtPct(fundamentals.profit_margin),      tip: "Net Profit Margin" },
    { label: "ROE",      val: fmtPct(fundamentals.return_on_equity),   tip: "Return on Equity" },
    { label: "Rev Grow", val: fmtPct(fundamentals.revenue_growth),     tip: "Revenue Growth YoY" },
    { label: "Yield",    val: fmtPct(fundamentals.dividend_yield),     tip: "Dividend Yield" },
  ].filter(m => m.val !== "—");

  if (metrics.length === 0) return null;

  return (
    <Box sx={{ mb: 1.5, p: 1.5, borderRadius: 2, background: c.bg, border: `1px solid ${c.border}` }}>
      {/* Valuation header */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="caption" fontWeight={700} sx={{ color: "text.secondary", letterSpacing: 0.5 }}>
          FUNDAMENTALS
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          {score !== undefined && (
            <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.65rem" }}>
              score {score}/100
            </Typography>
          )}
          <Chip
            label={status}
            size="small"
            sx={{ background: c.bg, color: c.text, border: `1px solid ${c.border}`, fontWeight: 800, fontSize: "0.68rem", height: 18 }}
          />
        </Box>
      </Box>

      {/* Valuation reason */}
      {valuation?.summary_reasons?.[0] && (
        <Typography variant="caption" sx={{ color: c.text, opacity: 0.85, display: "block", mb: 1, fontSize: "0.68rem" }}>
          {valuation.summary_reasons[0]}
        </Typography>
      )}

      {/* Metric chips */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
        {metrics.map((m) => (
          <Tooltip key={m.label} title={m.tip} arrow>
            <Box sx={{
              px: 0.75, py: 0.25, borderRadius: 1,
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.08)",
              display: "flex", gap: 0.5, alignItems: "baseline",
            }}>
              <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.62rem", fontWeight: 600 }}>
                {m.label}
              </Typography>
              <Typography variant="caption" sx={{ color: "text.primary", fontSize: "0.7rem", fontWeight: 700, fontFamily: "monospace" }}>
                {m.val}
              </Typography>
            </Box>
          </Tooltip>
        ))}
      </Box>
    </Box>
  );
}

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
  const pct = Math.min(dip.dip_pct, 25);

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
        sx={{ "& .MuiLinearProgress-bar": { background: `linear-gradient(90deg, ${color}88, ${color})`, borderRadius: 4 } }}
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
  if (nearest && current > 0) proxPct = Math.min(((nearest - current) / current) * 100, 20);

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={600}>RESISTANCE</Typography>
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
        sx={{ "& .MuiLinearProgress-bar": { background: "linear-gradient(90deg, #00b4d888, #00b4d8)", borderRadius: 4 } }}
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
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (!stock) return null;

  const {
    signal, dip, resistance_levels, support_levels,
    current_price, price_change_pct, price_change,
    sparkline, rsi, moving_averages, news, currency,
    fifty_two_week_high, fifty_two_week_low, name, symbol, error,
    fundamentals, valuation,
  } = stock;

  const isPositive = price_change_pct >= 0;
  const PriceIcon = isPositive ? TrendingUpIcon : TrendingDownIcon;
  const priceColor = isPositive ? "#00e676" : "#ff5252";
  const fullLabel = name && name !== symbol ? `${symbol} · ${name}` : symbol;

  if (error) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" color="text.secondary">{symbol}</Typography>
          <Typography variant="caption" color="error">Failed to load: {error}</Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardContent sx={{ p: 2.5 }}>
          {/* Header */}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 1, mb: 1.5 }}>
            {/* Left: symbol + name — constrained so it never pushes the right side */}
            <Tooltip title={fullLabel} placement="top" arrow>
              <Box sx={{ minWidth: 0, flex: 1, overflow: "hidden" }}>
                <Typography
                  variant="h6"
                  fontWeight={800}
                  noWrap
                  sx={{ lineHeight: 1.1, overflow: "hidden", textOverflow: "ellipsis" }}
                >
                  {symbol}
                </Typography>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  noWrap
                  sx={{ display: "block", overflow: "hidden", textOverflow: "ellipsis" }}
                >
                  {name}
                </Typography>
              </Box>
            </Tooltip>
            {/* Right: signal badge + delete — flex-shrink:0 so it never gets squashed */}
            <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.5, flexShrink: 0 }}>
              <SignalBadge signal={signal?.signal} confidence={signal?.confidence} size="small" />
              <Tooltip title="Remove stock">
                <IconButton
                  size="small"
                  onClick={() => setConfirmOpen(true)}
                  sx={{ color: "error.main", opacity: 0.5, "&:hover": { opacity: 1 } }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Tooltip>
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
                fontWeight: 700, fontSize: "0.75rem", height: 22,
              }}
            />
          </Box>

          {/* Sparkline */}
          <Box sx={{ mx: -1, mb: 1 }}>
            <Sparkline data={sparkline} positive={isPositive} currency={currency} />
          </Box>

          <Divider sx={{ borderColor: "rgba(255,255,255,0.06)", mb: 1.5 }} />

          <Box sx={{ mb: 1.5 }}><DipMeter dip={dip} currency={currency} /></Box>
          <Box sx={{ mb: 1.5 }}>
            <ResistanceMeter current={current_price} resistanceLevels={resistance_levels} supportLevels={support_levels} currency={currency} />
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
                    border: "1px solid rgba(255,255,255,0.08)", fontWeight: 700, fontSize: "0.72rem", height: 20,
                  }}
                />
              </Tooltip>
            )}
            {moving_averages?.ma20 && (
              <Tooltip title="20-day Moving Average">
                <Chip
                  label={`MA20: ${formatPrice(moving_averages.ma20, currency)}`}
                  size="small"
                  sx={{ background: "rgba(255,255,255,0.04)", color: "text.secondary", border: "1px solid rgba(255,255,255,0.08)", fontWeight: 600, fontSize: "0.72rem", height: 20 }}
                />
              </Tooltip>
            )}
            {fifty_two_week_high > 0 && (
              <Tooltip title="52-week range">
                <Chip
                  label={`52w: ${formatPrice(fifty_two_week_low, currency)} – ${formatPrice(fifty_two_week_high, currency)}`}
                  size="small"
                  sx={{ background: "rgba(255,255,255,0.04)", color: "text.secondary", border: "1px solid rgba(255,255,255,0.08)", fontSize: "0.68rem", fontWeight: 600, height: 20 }}
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

          {/* Fundamentals Panel */}
          <FundamentalPanel fundamentals={fundamentals} valuation={valuation} />

          <Divider sx={{ borderColor: "rgba(255,255,255,0.06)", mb: 1 }} />
          <NewsPanel news={news} />
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmOpen}
        title="Remove from watchlist?"
        message={`"${name || symbol}" will be moved to Trash. You can restore it later.`}
        confirmLabel="Move to Trash"
        danger
        onConfirm={() => { setConfirmOpen(false); onRemove(symbol); }}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
