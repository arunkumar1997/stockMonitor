import React from "react";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import ArticleIcon from "@mui/icons-material/Article";
import SettingsIcon from "@mui/icons-material/Settings";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import BrightnessAutoIcon from "@mui/icons-material/BrightnessAuto";
import { useThemeMode } from "../ThemeContext";

function ThemeToggle() {
  const { themeMode, setThemeMode } = useThemeMode();
  const cycle = () => {
    if (themeMode === "dark") setThemeMode("light");
    else if (themeMode === "light") setThemeMode("auto");
    else setThemeMode("dark");
  };
  const Icon =
    themeMode === "dark" ? DarkModeIcon
    : themeMode === "light" ? LightModeIcon
    : BrightnessAutoIcon;
  const label =
    themeMode === "dark" ? "Dark mode"
    : themeMode === "light" ? "Light mode"
    : "Auto (system)";
  return (
    <Tooltip title={label}>
      <IconButton
        onClick={cycle}
        size="small"
        sx={{ color: "primary.main", border: "1px solid rgba(0,180,216,0.25)" }}
      >
        <Icon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}

/**
 * The refresh / trash / logs / settings / theme icon cluster in the header.
 *
 * Wrapped in React.memo so the cluster does not re-render when unrelated
 * Dashboard state changes. All handlers passed in from Dashboard must be
 * stable (useCallback) for the memoization to be effective.
 */
function HeaderActions({
  refreshing,
  onRefresh,
  onOpenTrash,
  onOpenLogs,
  onOpenSettings,
}) {
  return (
    <>
      {/* Refresh */}
      <Tooltip title="Refresh now">
        <IconButton
          onClick={onRefresh}
          disabled={refreshing}
          size="small"
          sx={{
            color: "primary.main",
            border: "1px solid rgba(0,180,216,0.25)",
            animation: refreshing ? "spin 1s linear infinite" : "none",
            "@keyframes spin": { "100%": { transform: "rotate(360deg)" } },
          }}
        >
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Trash */}
      <Tooltip title="Trash (deleted stocks)">
        <IconButton
          onClick={onOpenTrash}
          size="small"
          sx={{ color: "error.main", border: "1px solid rgba(255,82,82,0.25)" }}
        >
          <DeleteSweepIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Logs */}
      <Tooltip title="Refresh Logs">
        <IconButton
          onClick={onOpenLogs}
          size="small"
          sx={{ color: "text.secondary", border: "1px solid rgba(128,128,128,0.25)" }}
        >
          <ArticleIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Settings */}
      <Tooltip title="Settings">
        <IconButton
          onClick={onOpenSettings}
          size="small"
          sx={{ color: "text.secondary", border: "1px solid rgba(128,128,128,0.25)" }}
        >
          <SettingsIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Theme toggle */}
      <ThemeToggle />
    </>
  );
}

export default React.memo(HeaderActions);
