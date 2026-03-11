import React, { createContext, useContext, useState, useEffect, useMemo } from "react";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";

const ThemeContext = createContext(null);

export function useThemeMode() {
  return useContext(ThemeContext);
}

function buildTheme(mode) {
  const isDark = mode === "dark";
  return createTheme({
    palette: {
      mode,
      primary: { main: "#00b4d8" },
      secondary: { main: "#7209b7" },
      background: isDark
        ? { default: "#080c18", paper: "#0f1626" }
        : { default: "#f0f4f8", paper: "#ffffff" },
      success: { main: "#00e676" },
      error: { main: "#ff5252" },
      warning: { main: "#ffd740" },
      text: isDark
        ? { primary: "#e8eaf6", secondary: "#90a4ae" }
        : { primary: "#1a202c", secondary: "#4a5568" },
    },
    typography: {
      fontFamily: "'Inter', 'Roboto', sans-serif",
      h4: { fontWeight: 800, letterSpacing: "-0.5px" },
      h5: { fontWeight: 700 },
      h6: { fontWeight: 700 },
      subtitle1: { fontWeight: 600 },
      subtitle2: { fontWeight: 600, letterSpacing: "0.5px" },
    },
    shape: { borderRadius: 16 },
    components: {
      MuiCard: {
        styleOverrides: {
          root: {
            background: isDark
              ? "linear-gradient(145deg, rgba(15,22,38,0.9) 0%, rgba(10,14,26,0.95) 100%)"
              : "linear-gradient(145deg, #ffffff 0%, #f7fafc 100%)",
            backdropFilter: "blur(20px)",
            border: isDark
              ? "1px solid rgba(0,180,216,0.12)"
              : "1px solid rgba(0,180,216,0.18)",
            transition: "transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease",
            "&:hover": {
              transform: "translateY(-4px)",
              boxShadow: "0 20px 60px rgba(0,180,216,0.15)",
              borderColor: "rgba(0,180,216,0.3)",
            },
          },
        },
      },
      MuiChip: {
        styleOverrides: { root: { fontWeight: 700, letterSpacing: "0.5px" } },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            borderRadius: 4,
            height: 6,
            backgroundColor: isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)",
          },
        },
      },
      MuiAccordion: {
        styleOverrides: {
          root: { background: "transparent", boxShadow: "none", "&:before": { display: "none" } },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: {
            background: isDark
              ? "linear-gradient(145deg, #0f1626 0%, #080c18 100%)"
              : "linear-gradient(145deg, #ffffff 0%, #f7fafc 100%)",
            border: "1px solid rgba(0,180,216,0.2)",
          },
        },
      },
    },
  });
}

export function AppThemeProvider({ children }) {
  const [themeMode, setThemeModeRaw] = useState(
    () => localStorage.getItem("themeMode") || "dark"
  );

  // Determine effective mode when "auto"
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e) => setSystemDark(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const effectiveMode = themeMode === "auto" ? (systemDark ? "dark" : "light") : themeMode;

  const theme = useMemo(() => buildTheme(effectiveMode), [effectiveMode]);

  const setThemeMode = (mode) => {
    setThemeModeRaw(mode);
    localStorage.setItem("themeMode", mode);
  };

  return (
    <ThemeContext.Provider value={{ themeMode, setThemeMode, effectiveMode }}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </ThemeContext.Provider>
  );
}
