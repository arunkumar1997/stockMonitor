import React from "react";
import { AppThemeProvider } from "./ThemeContext";
import Dashboard from "./components/Dashboard";

export default function App() {
  return (
    <AppThemeProvider>
      <Dashboard />
    </AppThemeProvider>
  );
}
