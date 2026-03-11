import React, { useEffect, useState } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import CloseIcon from "@mui/icons-material/Close";
import RestoreIcon from "@mui/icons-material/Restore";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import ConfirmDialog from "./ConfirmDialog";
import { getDeletedStocks, restoreStock, purgeStock } from "../api";
import { useSnackbar } from "notistack";

export default function TrashPage({ open, onClose, onRestored }) {
  const [deleted, setDeleted] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [confirmState, setConfirmState] = useState({ open: false, symbol: null, action: null });
  const { enqueueSnackbar } = useSnackbar();

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getDeletedStocks();
      setDeleted(data);
    } catch {
      setError("Failed to load deleted stocks.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) load();
  }, [open]);

  const handleRestore = async (symbol) => {
    try {
      await restoreStock(symbol);
      enqueueSnackbar(`${symbol} restored to watchlist`, { variant: "success" });
      await load();
      onRestored?.();
    } catch {
      enqueueSnackbar(`Failed to restore ${symbol}`, { variant: "error" });
    }
  };

  const handlePurge = async (symbol) => {
    try {
      await purgeStock(symbol);
      enqueueSnackbar(`${symbol} permanently deleted`, { variant: "info" });
      await load();
    } catch {
      enqueueSnackbar(`Failed to delete ${symbol}`, { variant: "error" });
    }
  };

  const openConfirm = (symbol, action) =>
    setConfirmState({ open: true, symbol, action });

  const handleConfirm = () => {
    const { symbol, action } = confirmState;
    setConfirmState({ open: false, symbol: null, action: null });
    if (action === "purge") handlePurge(symbol);
    if (action === "restore") handleRestore(symbol);
  };

  const formatDate = (ts) =>
    ts ? new Date(ts * 1000).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—";

  return (
    <>
      <Drawer
        anchor="right"
        open={open}
        onClose={onClose}
        PaperProps={{
          sx: {
            width: { xs: "100vw", sm: 420 },
            background: (t) =>
              t.palette.mode === "dark"
                ? "linear-gradient(160deg, #0f1626 0%, #080c18 100%)"
                : "#f7fafc",
            borderLeft: "1px solid rgba(0,180,216,0.15)",
          },
        }}
      >
        {/* Header */}
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 3, py: 2.5, borderBottom: "1px solid rgba(0,180,216,0.1)" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <DeleteSweepIcon sx={{ color: "error.main" }} />
            <Typography variant="h6" fontWeight={800}>Trash</Typography>
            {deleted.length > 0 && (
              <Chip label={deleted.length} size="small" sx={{ background: "rgba(255,82,82,0.15)", color: "error.main", fontWeight: 700, height: 20 }} />
            )}
          </Box>
          <IconButton onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Box>

        {/* Body */}
        <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
          {loading && (
            <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
              <CircularProgress />
            </Box>
          )}
          {error && <Alert severity="error" sx={{ borderRadius: 2 }}>{error}</Alert>}
          {!loading && !error && deleted.length === 0 && (
            <Box sx={{ textAlign: "center", mt: 8 }}>
              <DeleteSweepIcon sx={{ fontSize: 56, color: "rgba(255,255,255,0.1)", mb: 2 }} />
              <Typography color="text.secondary">Trash is empty</Typography>
            </Box>
          )}
          {!loading && deleted.map((s, i) => (
            <Box key={s.symbol}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 1.5, px: 1 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="subtitle2" fontWeight={800} sx={{ lineHeight: 1.2 }}>
                    {s.symbol}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" noWrap>{s.name}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                    🗑 Deleted {formatDate(s.deleted_at)}
                  </Typography>
                  <Chip label={s.sector} size="small" sx={{ mt: 0.5, height: 18, fontSize: "0.65rem", background: "rgba(0,180,216,0.1)", color: "primary.main" }} />
                </Box>
                <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0 }}>
                  <Tooltip title="Restore to watchlist">
                    <IconButton
                      size="small"
                      onClick={() => openConfirm(s.symbol, "restore")}
                      sx={{ color: "success.main", border: "1px solid rgba(0,230,118,0.2)", "&:hover": { background: "rgba(0,230,118,0.1)" } }}
                    >
                      <RestoreIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete permanently">
                    <IconButton
                      size="small"
                      onClick={() => openConfirm(s.symbol, "purge")}
                      sx={{ color: "error.main", border: "1px solid rgba(255,82,82,0.2)", "&:hover": { background: "rgba(255,82,82,0.1)" } }}
                    >
                      <DeleteForeverIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
              {i < deleted.length - 1 && <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />}
            </Box>
          ))}
        </Box>
      </Drawer>

      <ConfirmDialog
        open={confirmState.open}
        title={confirmState.action === "purge" ? "Delete permanently?" : "Restore stock?"}
        message={
          confirmState.action === "purge"
            ? `${confirmState.symbol} will be permanently removed from the watchlist and all cached data will be erased. This cannot be undone.`
            : `${confirmState.symbol} will be restored to your active watchlist and refreshed.`
        }
        confirmLabel={confirmState.action === "purge" ? "Delete Forever" : "Restore"}
        danger={confirmState.action === "purge"}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmState({ open: false, symbol: null, action: null })}
      />
    </>
  );
}
