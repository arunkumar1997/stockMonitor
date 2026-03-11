import React from "react";
import ReactDOM from "react-dom/client";
import { SnackbarProvider } from "notistack";
import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <SnackbarProvider
      maxSnack={4}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      autoHideDuration={3500}
    >
      <App />
    </SnackbarProvider>
  </React.StrictMode>
);
