import React from "react";
import { AppThemeProvider } from "./ThemeContext";
import Dashboard from "./components/Dashboard";
import { SchedulerEventsProvider } from "./hooks/SchedulerEventsProvider";

export default function App() {
  return (
    <AppThemeProvider>
      <SchedulerEventsProvider>
        <Dashboard />
      </SchedulerEventsProvider>
    </AppThemeProvider>
  );
}
