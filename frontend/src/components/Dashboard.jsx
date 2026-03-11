import React, { useEffect, useState, useCallback, useRef } from "react";
import Grid from "@mui/material/Grid";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Skeleton from "@mui/material/Skeleton";
import Fab from "@mui/material/Fab";
import Tooltip from "@mui/material/Tooltip";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import Collapse from "@mui/material/Collapse";
import AddIcon from "@mui/icons-material/Add";
import RefreshIcon from "@mui/icons-material/Refresh";
import ShowChartIcon from "@mui/icons-material/ShowChart";
import SearchIcon from "@mui/icons-material/Search";
import ClearIcon from "@mui/icons-material/Clear";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import BrightnessAutoIcon from "@mui/icons-material/BrightnessAuto";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import SettingsIcon from "@mui/icons-material/Settings";
import ArticleIcon from "@mui/icons-material/Article";
import StockCard from "./StockCard";
import AddStockModal from "./AddStockModal";
import TrashPage from "./TrashPage";
import SettingsPage from "./SettingsPage";
import LogsPanel from "./LogsPanel";
import { getDashboard, addStock, removeStock, getSchedulerStatus } from "../api";
import { useThemeMode } from "../ThemeContext";
import { useSnackbar } from "notistack";

const REFRESH_INTERVAL = 300;

const SECTOR_ICONS = {
  "Pharma": "💊",
  "Defence": "🛡️",
  "Electronics": "🔌",
  "Infra / Power": "⚡",
  "Autos": "🚗",
  "IT": "💻",
  "Banks": "🏦",
  "Penny Pharma": "🧪",
  "ETF": "📊",
};

const SIGNAL_COLORS = {
  BUY: "#00e676", "BUY SMALL": "#69f0ae",
  WAIT: "#ffd740", AVOID: "#ff5252", HOLD: "#ffd740",
};

function ThemeToggle() {
  const { themeMode, setThemeMode } = useThemeMode();
  const cycle = () => {
    if (themeMode === "dark") setThemeMode("light");
    else if (themeMode === "light") setThemeMode("auto");
    else setThemeMode("dark");
  };
  const Icon = themeMode === "dark" ? DarkModeIcon : themeMode === "light" ? LightModeIcon : BrightnessAutoIcon;
  const label = themeMode === "dark" ? "Dark mode" : themeMode === "light" ? "Light mode" : "Auto (system)";
  return (
    <Tooltip title={label}>
      <IconButton onClick={cycle} size="small" sx={{ color: "primary.main", border: "1px solid rgba(0,180,216,0.25)" }}>
        <Icon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}

function CardSkeleton() {
  return (
    <Box sx={{ borderRadius: 4, overflow: "hidden", border: "1px solid rgba(0,180,216,0.1)", p: 2.5 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1.5 }}>
        <Box>
          <Skeleton variant="text" width={80} height={32} sx={{ bgcolor: "rgba(255,255,255,0.06)" }} />
          <Skeleton variant="text" width={140} height={18} sx={{ bgcolor: "rgba(255,255,255,0.04)" }} />
        </Box>
        <Skeleton variant="rounded" width={100} height={26} sx={{ bgcolor: "rgba(255,255,255,0.06)" }} />
      </Box>
      <Skeleton variant="text" width={120} height={40} sx={{ bgcolor: "rgba(255,255,255,0.06)" }} />
      <Skeleton variant="rounded" width="100%" height={70} sx={{ bgcolor: "rgba(255,255,255,0.04)", mb: 1.5, mt: 1 }} />
      <Skeleton variant="rounded" width="100%" height={6} sx={{ bgcolor: "rgba(255,255,255,0.06)", mb: 0.5 }} />
      <Skeleton variant="rounded" width="100%" height={6} sx={{ bgcolor: "rgba(255,255,255,0.04)" }} />
    </Box>
  );
}

function SectorSection({ sector, sectorStocks, onRemove, collapsed, onToggleCollapse }) {
  return (
    <Box sx={{ mb: 5 }}>
      {/* Sector header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2, cursor: "pointer" }} onClick={onToggleCollapse}>
        <IconButton size="small" sx={{ color: "text.secondary", p: 0.25 }}>
          {collapsed ? <ExpandMoreIcon fontSize="small" /> : <ExpandLessIcon fontSize="small" />}
        </IconButton>
        <Typography variant="h6" sx={{ color: "primary.main", fontWeight: 800 }}>
          {SECTOR_ICONS[sector] || "📌"} {sector}
        </Typography>
        <Chip label={`${sectorStocks.length} stocks`} size="small" sx={{
          background: "rgba(0,180,216,0.1)", color: "primary.main",
          border: "1px solid rgba(0,180,216,0.2)", fontWeight: 600, fontSize: "0.7rem",
        }} />
        {Object.entries(
          sectorStocks.reduce((a, s) => {
            const sig = s.signal?.signal || "WAIT";
            a[sig] = (a[sig] || 0) + 1;
            return a;
          }, {})
        ).map(([sig, cnt]) => (
          <Chip key={sig} label={`${sig} ×${cnt}`} size="small" sx={{
            color: SIGNAL_COLORS[sig] || "#90a4ae",
            border: `1px solid ${SIGNAL_COLORS[sig] || "#90a4ae"}30`,
            background: `${SIGNAL_COLORS[sig] || "#90a4ae"}0e`,
            fontWeight: 700, fontSize: "0.68rem", height: 20,
          }} />
        ))}
      </Box>
      <Divider sx={{ borderColor: "rgba(0,180,216,0.1)", mb: 2 }} />
      <Collapse in={!collapsed} timeout="auto">
        <Grid container spacing={2.5}>
          {sectorStocks.map((stock) => (
            <Grid key={stock.symbol} size={{ xs: 12, sm: 6, md: 4, lg: 3, xl: 2 }}>
              <StockCard stock={stock} onRemove={onRemove} />
            </Grid>
          ))}
        </Grid>
      </Collapse>
    </Box>
  );
}

export default function Dashboard() {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [trashOpen,    setTrashOpen]    = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [logsOpen,     setLogsOpen]     = useState(false);
  const [countdown, setCountdown] = useState(REFRESH_INTERVAL);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [collapsedSectors, setCollapsedSectors] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("collapsedSectors") || "{}");
    } catch { return {}; }
  });

  const { enqueueSnackbar } = useSnackbar();
  const searchRef = useRef(null);

  const fetchDashboard = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const [data, status] = await Promise.all([
        getDashboard(),
        getSchedulerStatus().catch(() => null),
      ]);
      setStocks(data);
      setSchedulerStatus(status);
      setLastUpdated(new Date());
      setCountdown(REFRESH_INTERVAL);
    } catch {
      setError("Cannot connect to backend. Make sure the Python server is running on port 8000.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  useEffect(() => {
    const tick = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) { fetchDashboard(true); return REFRESH_INTERVAL; }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(tick);
  }, [fetchDashboard]);

  const handleAdd = async (symbol, name, sector) => {
    await addStock(symbol, name, sector);
    await fetchDashboard(true);
    enqueueSnackbar(`${symbol} added to watchlist`, { variant: "success" });
  };

  const handleRemove = async (symbol) => {
    await removeStock(symbol);
    setStocks((prev) => prev.filter((s) => s.symbol !== symbol));
    enqueueSnackbar(`${symbol} moved to Trash`, { variant: "info" });
  };

  const toggleSectorCollapse = (sector) => {
    setCollapsedSectors((prev) => {
      const next = { ...prev, [sector]: !prev[sector] };
      localStorage.setItem("collapsedSectors", JSON.stringify(next));
      return next;
    });
  };

  // Search filtering
  const q = searchQuery.trim().toLowerCase();
  const filteredStocks = q
    ? stocks.filter((s) =>
        s.symbol.toLowerCase().includes(q) || (s.name || "").toLowerCase().includes(q)
      )
    : stocks;

  // Group by sector
  const grouped = filteredStocks.reduce((acc, stock) => {
    const sector = stock.sector || "Other";
    if (!acc[sector]) acc[sector] = [];
    acc[sector].push(stock);
    return acc;
  }, {});

  const signalCounts = stocks.reduce((acc, s) => {
    const sig = s.signal?.signal || "WAIT";
    acc[sig] = (acc[sig] || 0) + 1;
    return acc;
  }, {});

  return (
    <Box sx={{ minHeight: "100vh", pb: 10 }}>
      {/* Header */}
      <Box sx={{
        background: "linear-gradient(180deg, rgba(0,180,216,0.08) 0%, transparent 100%)",
        borderBottom: "1px solid rgba(0,180,216,0.1)",
        px: { xs: 2, md: 4 }, py: 2.5, mb: 4,
      }}>
        {/* Top row: Logo + actions */}
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 2, mb: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <ShowChartIcon sx={{ fontSize: 32, color: "primary.main" }} />
            <Box>
              <Typography variant="h4" sx={{
                background: "linear-gradient(135deg, #00b4d8, #7209b7)",
                WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
              }}>
                DipSense
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Indian Stock Monitor · {stocks.length} stocks · {Object.keys(grouped).length} sectors
              </Typography>
            </Box>
          </Box>

          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            {/* Signal counts */}
            {Object.entries(signalCounts).map(([sig, count]) => (
              <Chip key={sig} label={`${sig}: ${count}`} size="small" sx={{
                color: SIGNAL_COLORS[sig] || "#90a4ae",
                border: `1px solid ${SIGNAL_COLORS[sig] || "#90a4ae"}40`,
                background: `${SIGNAL_COLORS[sig] || "#90a4ae"}12`,
                fontWeight: 700, fontSize: "0.72rem",
              }} />
            ))}

            {/* Scheduler live status */}
            {schedulerStatus?.current_symbol && (
              <Chip
                label={`⟳ fetching ${schedulerStatus.current_symbol}`}
                size="small"
                sx={{
                  background: "rgba(0,180,216,0.12)", color: "#00b4d8",
                  border: "1px solid rgba(0,180,216,0.3)",
                  fontWeight: 700, fontSize: "0.72rem",
                  animation: "pulse 1.4s ease-in-out infinite",
                  "@keyframes pulse": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.5 } },
                }}
              />
            )}

            {lastUpdated && (
              <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                Updated {lastUpdated.toLocaleTimeString()} · {countdown}s
              </Typography>
            )}

            {/* Refresh */}
            <Tooltip title="Refresh now">
              <IconButton onClick={() => fetchDashboard(true)} disabled={refreshing} size="small" sx={{
                color: "primary.main", border: "1px solid rgba(0,180,216,0.25)",
                animation: refreshing ? "spin 1s linear infinite" : "none",
                "@keyframes spin": { "100%": { transform: "rotate(360deg)" } },
              }}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>

            {/* Trash */}
            <Tooltip title="Trash (deleted stocks)">
              <IconButton onClick={() => setTrashOpen(true)} size="small" sx={{ color: "error.main", border: "1px solid rgba(255,82,82,0.25)" }}>
                <DeleteSweepIcon fontSize="small" />
              </IconButton>
            </Tooltip>

            {/* Logs */}
            <Tooltip title="Refresh Logs">
              <IconButton onClick={() => setLogsOpen(true)} size="small" sx={{ color: "text.secondary", border: "1px solid rgba(128,128,128,0.25)" }}>
                <ArticleIcon fontSize="small" />
              </IconButton>
            </Tooltip>

            {/* Settings */}
            <Tooltip title="Settings">
              <IconButton onClick={() => setSettingsOpen(true)} size="small" sx={{ color: "text.secondary", border: "1px solid rgba(128,128,128,0.25)" }}>
                <SettingsIcon fontSize="small" />
              </IconButton>
            </Tooltip>

            {/* Theme toggle */}
            <ThemeToggle />
          </Box>
        </Box>

        {/* Search bar */}
        <TextField
          inputRef={searchRef}
          placeholder="Search by symbol or company name…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          size="small"
          fullWidth
          sx={{ maxWidth: 480 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon sx={{ color: "text.secondary", fontSize: 20 }} />
              </InputAdornment>
            ),
            endAdornment: searchQuery ? (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => setSearchQuery("")}>
                  <ClearIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ) : null,
          }}
        />
        {q && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            {filteredStocks.length} result{filteredStocks.length !== 1 ? "s" : ""} for "{searchQuery}"
          </Typography>
        )}
      </Box>

      {/* Content */}
      <Box sx={{ px: { xs: 2, md: 4 } }}>
        {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 3 }}>{error}</Alert>}

        {loading ? (
          <Grid container spacing={2.5}>
            {Array.from({ length: 8 }).map((_, i) => (
              <Grid key={i} size={{ xs: 12, sm: 6, md: 4, lg: 3, xl: 2 }}>
                <CardSkeleton />
              </Grid>
            ))}
          </Grid>
        ) : (
          Object.entries(grouped).map(([sector, sectorStocks]) => (
            <SectorSection
              key={sector}
              sector={sector}
              sectorStocks={sectorStocks}
              onRemove={handleRemove}
              collapsed={!!collapsedSectors[sector]}
              onToggleCollapse={() => toggleSectorCollapse(sector)}
            />
          ))
        )}

        {!loading && filteredStocks.length === 0 && !error && (
          <Box sx={{ textAlign: "center", mt: 10 }}>
            <ShowChartIcon sx={{ fontSize: 64, color: "rgba(255,255,255,0.1)", mb: 2 }} />
            <Typography variant="h6" color="text.secondary">
              {q ? `No stocks match "${searchQuery}"` : "No stocks tracked yet"}
            </Typography>
          </Box>
        )}
      </Box>

      {/* FAB */}
      <Tooltip title="Add stock">
        <Fab color="primary" onClick={() => setModalOpen(true)} sx={{
          position: "fixed", bottom: 32, right: 32,
          background: "linear-gradient(135deg, #00b4d8, #7209b7)",
          boxShadow: "0 8px 32px rgba(0,180,216,0.4)",
          "&:hover": { transform: "scale(1.08)", boxShadow: "0 12px 40px rgba(0,180,216,0.5)" },
          transition: "all 0.2s ease",
        }}>
          <AddIcon />
        </Fab>
      </Tooltip>

      <AddStockModal open={modalOpen} onClose={() => setModalOpen(false)} onAdd={handleAdd} />
      <TrashPage open={trashOpen} onClose={() => setTrashOpen(false)} onRestored={() => fetchDashboard(true)} />
      <SettingsPage open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <LogsPanel open={logsOpen} onClose={() => setLogsOpen(false)} />
    </Box>
  );
}
