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
import AddchartIcon from "@mui/icons-material/Addchart";

export default function AddStockModal({ open, onClose, onAdd }) {
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!symbol.trim()) { setError("Symbol is required"); return; }
    setLoading(true);
    setError("");
    try {
      await onAdd(symbol.trim().toUpperCase(), name.trim() || symbol.trim().toUpperCase());
      setSymbol("");
      setName("");
      onClose();
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to add stock");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
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
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
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
