// SPDX-License-Identifier: Apache-2.0
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { applyThemePreference, readThemePreference } from "./lib/theme";

// P33.20 : le réglage de thème est posé avant le premier rendu React.
applyThemePreference(readThemePreference());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
