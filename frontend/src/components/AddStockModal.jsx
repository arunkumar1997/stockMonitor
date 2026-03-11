import React, { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import Tooltip from "@mui/material/Tooltip";
import AddchartIcon from "@mui/icons-material/Addchart";

// ── Category definitions with emoji icons ────────────────────────────────────
const SECTORS = [
  { label: "Banks",         icon: "🏦" },
  { label: "IT",            icon: "💻" },
  { label: "Pharma",        icon: "💊" },
  { label: "Autos",         icon: "🚗" },
  { label: "Defence",       icon: "🛡️" },
  { label: "Electronics",   icon: "🔌" },
  { label: "Infra / Power", icon: "⚡" },
  { label: "ETF",           icon: "📊" },
  { label: "Penny Pharma",  icon: "🧪" },
  { label: "FMCG",          icon: "🛒" },
  { label: "Metals",        icon: "🪨" },
  { label: "Realty",        icon: "🏗️" },
  { label: "Energy",        icon: "🛢️" },
  { label: "Fintech",       icon: "💳" },
  { label: "Other",         icon: "🗂️" },
];

function SectorChip({ sector, selected, onClick }) {
  return (
    <Tooltip title={sector.label} arrow>
      <Box
        onClick={onClick}
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 0.4,
          px: 1,
          py: 0.75,
          borderRadius: 2,
          cursor: "pointer",
          transition: "all 0.15s ease",
          minWidth: 56,
          border: selected
            ? "1.5px solid"
            : "1.5px solid transparent",
          borderColor: selected ? "primary.main" : "transparent",
          background: selected
            ? "rgba(144,202,249,0.12)"
            : "rgba(255,255,255,0.04)",
          "&:hover": {
            background: selected
              ? "rgba(144,202,249,0.18)"
              : "rgba(255,255,255,0.08)",
            transform: "translateY(-1px)",
          },
        }}
      >
        <Typography sx={{ fontSize: "1.35rem", lineHeight: 1 }}>
          {sector.icon}
        </Typography>
        <Typography
          variant="caption"
          sx={{
            fontSize: "0.58rem",
            fontWeight: selected ? 800 : 500,
            color: selected ? "primary.main" : "text.secondary",
            lineHeight: 1.2,
            textAlign: "center",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: 54,
          }}
        >
          {sector.label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

export default function AddStockModal({ open, onClose, onAdd }) {
  const [symbol, setSymbol]   = useState("");
  const [name,   setName]     = useState("");
  const [sector, setSector]   = useState("Other");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const handleSubmit = async () => {
    if (!symbol.trim()) { setError("Symbol is required"); return; }
    setLoading(true);
    setError("");
    try {
      await onAdd(
        symbol.trim().toUpperCase(),
        name.trim() || symbol.trim().toUpperCase(),
        sector,
      );
      setSymbol("");
      setName("");
      setSector("Other");
      onClose();
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to add stock");
    } finally {
      setLoading(false);
    }
  };

  const selectedSector = SECTORS.find((s) => s.label === sector) || SECTORS[SECTORS.length - 1];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.5, pb: 1 }}>
        <AddchartIcon sx={{ color: "primary.main" }} />
        <Box>
          <Typography variant="h6" fontWeight={800}>Add Stock</Typography>
          <Typography variant="caption" color="text.secondary">
            US: <code>AAPL</code> · NSE: <code>RELIANCE.NS</code> · BSE: <code>RELIANCE.BO</code>
          </Typography>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ pt: 1 }}>
        {error && <Alert severity="error" sx={{ mb: 2, borderRadius: 2 }}>{error}</Alert>}

        {/* Ticker + Name */}
        <TextField
          label="Ticker Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          fullWidth
          size="small"
          placeholder="e.g. AAPL or RELIANCE.NS"
          sx={{ mb: 2 }}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          inputProps={{ style: { fontFamily: "monospace", fontWeight: 700 } }}
        />
        <TextField
          label="Company Name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          fullWidth
          size="small"
          placeholder="e.g. Apple Inc"
          sx={{ mb: 2.5 }}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />

        {/* Category picker */}
        <Box sx={{ mb: 0.5, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ letterSpacing: 0.5 }}>
            CATEGORY
          </Typography>
          <Typography variant="caption" sx={{ color: "primary.main", fontWeight: 700 }}>
            {selectedSector.icon} {sector}
          </Typography>
        </Box>
        <Box
          sx={{
            display: "flex",
            flexWrap: "wrap",
            gap: 0.5,
            p: 1.25,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "divider",
            background: "rgba(255,255,255,0.02)",
          }}
        >
          {SECTORS.map((s) => (
            <SectorChip
              key={s.label}
              sector={s}
              selected={sector === s.label}
              onClick={() => setSector(s.label)}
            />
          ))}
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} color="inherit" disabled={loading}>Cancel</Button>
        <Button
          onClick={handleSubmit}
          variant="contained"
          disabled={loading || !symbol.trim()}
          sx={{ fontWeight: 700 }}
        >
          {loading ? "Adding…" : "Add Stock"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
