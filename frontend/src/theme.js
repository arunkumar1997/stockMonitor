import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#00b4d8" },
    secondary: { main: "#7209b7" },
    background: {
      default: "#080c18",
      paper: "#0f1626",
    },
    success: { main: "#00e676" },
    error: { main: "#ff5252" },
    warning: { main: "#ffd740" },
    text: {
      primary: "#e8eaf6",
      secondary: "#90a4ae",
    },
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
          background:
            "linear-gradient(145deg, rgba(15,22,38,0.9) 0%, rgba(10,14,26,0.95) 100%)",
          backdropFilter: "blur(20px)",
          border: "1px solid rgba(0,180,216,0.12)",
          transition:
            "transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease",
          "&:hover": {
            transform: "translateY(-4px)",
            boxShadow: "0 20px 60px rgba(0,180,216,0.15)",
            borderColor: "rgba(0,180,216,0.3)",
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 700, letterSpacing: "0.5px" },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          height: 6,
          backgroundColor: "rgba(255,255,255,0.08)",
        },
      },
    },
    MuiAccordion: {
      styleOverrides: {
        root: {
          background: "transparent",
          boxShadow: "none",
          "&:before": { display: "none" },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          background: "linear-gradient(145deg, #0f1626 0%, #080c18 100%)",
          border: "1px solid rgba(0,180,216,0.2)",
        },
      },
    },
  },
});

export default theme;
