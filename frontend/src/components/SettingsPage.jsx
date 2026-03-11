import React, { useEffect, useState, useCallback } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import TextField from "@mui/material/TextField";
import Chip from "@mui/material/Chip";
import Slider from "@mui/material/Slider";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import CircularProgress from "@mui/material/CircularProgress";
import Tooltip from "@mui/material/Tooltip";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RestoreIcon from "@mui/icons-material/Restore";
import SaveIcon from "@mui/icons-material/Check";
import AddIcon from "@mui/icons-material/Add";
import { getConfig, updateConfig } from "../api";
import { useSnackbar } from "notistack";

const CATEGORY_ICONS = {
  "News & Sentiment": "📰",
  "Dip Detection": "📉",
  "Technical Analysis": "📈",
  "General": "🔧",
};

// ── Individual field editors ──────────────────────────────────────────────────

function KeywordChipEditor({ entry, onSave }) {
  const [keywords, setKeywords] = useState(entry.value || []);
  const [input, setInput]       = useState("");
  const [dirty, setDirty]       = useState(false);

  const handleAdd = () => {
    const kw = input.trim().toLowerCase();
    if (kw && !keywords.includes(kw)) {
      const next = [...keywords, kw].sort();
      setKeywords(next);
      setDirty(true);
    }
    setInput("");
  };

  const handleDelete = (kw) => {
    const next = keywords.filter((k) => k !== kw);
    setKeywords(next);
    setDirty(true);
  };

  return (
    <Box>
      <Box sx={{ display: "flex", gap: 1, mb: 1.5 }}>
        <TextField
          size="small"
          placeholder="Add keyword…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          sx={{ flex: 1 }}
        />
        <IconButton size="small" onClick={handleAdd} sx={{ color: "primary.main" }}>
          <AddIcon />
        </IconButton>
        {dirty && (
          <Tooltip title="Save changes">
            <IconButton size="small" color="success" onClick={() => { onSave(entry.key, keywords); setDirty(false); }}>
              <SaveIcon />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
        {keywords.map((kw) => (
          <Chip
            key={kw}
            label={kw}
            size="small"
            onDelete={() => handleDelete(kw)}
            sx={{ fontFamily: "monospace", fontSize: "0.72rem" }}
          />
        ))}
      </Box>
    </Box>
  );
}

function NumberField({ entry, onSave }) {
  const [val, setVal] = useState(entry.value);
  const dirty = val !== entry.value;

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <TextField
        size="small"
        type="number"
        value={val}
        onChange={(e) => setVal(entry.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value))}
        inputProps={{
          step: entry.type === "float" ? 0.05 : 1,
          min: 0,
        }}
        sx={{ width: 120 }}
      />
      {dirty && (
        <Tooltip title="Save">
          <IconButton size="small" color="success" onClick={() => onSave(entry.key, val)}>
            <SaveIcon />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  );
}

function SelectField({ entry, onSave }) {
  const OPTIONS = ["1mo", "3mo", "6mo", "1y", "2y"];
  const [val, setVal] = useState(entry.value);
  const dirty = val !== entry.value;

  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <FormControl size="small" sx={{ minWidth: 120 }}>
        <Select value={val} onChange={(e) => setVal(e.target.value)}>
          {OPTIONS.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
        </Select>
      </FormControl>
      {dirty && (
        <Tooltip title="Save">
          <IconButton size="small" color="success" onClick={() => onSave(entry.key, val)}>
            <SaveIcon />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  );
}

function ConfigField({ entry, onSave }) {
  if (entry.type === "json_list") return <KeywordChipEditor entry={entry} onSave={onSave} />;
  if (entry.key === "history_period") return <SelectField entry={entry} onSave={onSave} />;
  return <NumberField entry={entry} onSave={onSave} />;
}

// ── Settings Page Drawer ──────────────────────────────────────────────────────

export default function SettingsPage({ open, onClose }) {
  const [config, setConfig]   = useState(null);  // { "Category": [entries] }
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const { enqueueSnackbar }   = useSnackbar();

  const loadConfig = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await getConfig();
      setConfig(data);
    } catch {
      setError("Failed to load settings from backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (open) loadConfig(); }, [open, loadConfig]);

  const handleSave = async (key, value) => {
    try {
      await updateConfig(key, value);
      // Update local state to reflect saved value (clears dirty)
      setConfig((prev) => {
        if (!prev) return prev;
        const next = {};
        for (const [cat, entries] of Object.entries(prev)) {
          next[cat] = entries.map((e) => e.key === key ? { ...e, value } : e);
        }
        return next;
      });
      enqueueSnackbar("Setting saved", { variant: "success" });
    } catch {
      enqueueSnackbar("Failed to save setting", { variant: "error" });
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: { xs: "100vw", sm: 520 }, p: 0 } }}
    >
      {/* Header */}
      <Box sx={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        px: 3, py: 2,
        borderBottom: "1px solid",
        borderColor: "divider",
        background: "linear-gradient(135deg, rgba(0,180,216,0.08), transparent)",
      }}>
        <Box>
          <Typography variant="h6" fontWeight={800}>⚙️ Settings</Typography>
          <Typography variant="caption" color="text.secondary">
            All changes take effect on the next stock refresh
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Tooltip title="Reload settings">
            <IconButton size="small" onClick={loadConfig}><RestoreIcon fontSize="small" /></IconButton>
          </Tooltip>
          <IconButton size="small" onClick={onClose}><CloseIcon /></IconButton>
        </Box>
      </Box>

      {/* Body */}
      <Box sx={{ overflowY: "auto", p: 2 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", mt: 8 }}>
            <CircularProgress />
          </Box>
        ) : config ? (
          Object.entries(config).map(([category, entries]) => (
            <Accordion key={category} defaultExpanded disableGutters elevation={0}
              sx={{ mb: 1.5, border: "1px solid", borderColor: "divider", borderRadius: "12px !important", "&::before": { display: "none" } }}
            >
              <AccordionSummary expandIcon={<ExpandMoreIcon />}
                sx={{ borderRadius: "12px", px: 2.5, py: 0.5, "& .MuiAccordionSummary-content": { my: 1 } }}
              >
                <Typography fontWeight={700} fontSize="0.95rem">
                  {CATEGORY_ICONS[category] || "🔧"} {category}
                </Typography>
                <Chip label={`${entries.length}`} size="small" sx={{ ml: 1, height: 18, fontSize: "0.7rem" }} />
              </AccordionSummary>
              <AccordionDetails sx={{ px: 2.5, pb: 2 }}>
                {entries.map((entry, i) => (
                  <Box key={entry.key}>
                    {i > 0 && <Divider sx={{ my: 2, borderStyle: "dashed" }} />}
                    <Box sx={{ mb: 1.5 }}>
                      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mb: 0.5 }}>
                        <Typography variant="body2" fontWeight={700}>{entry.label}</Typography>
                        <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace" }}>
                          {entry.key}
                        </Typography>
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                        {entry.description}
                      </Typography>
                      <ConfigField entry={entry} onSave={handleSave} />
                    </Box>
                  </Box>
                ))}
              </AccordionDetails>
            </Accordion>
          ))
        ) : null}
      </Box>
    </Drawer>
  );
}
