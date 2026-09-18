// SPDX-License-Identifier: Apache-2.0
// Config Vite séparée de vite.config.ts, même patron que
// vite.export.config.ts (SP-18a) : ce build ne dépend jamais de la config
// de test, produit un artefact autonome consommé par
// desktop-etl/src-tauri/tauri.conf.json (build.frontendDist).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { resolve } from "node:path";
import { rename } from "node:fs/promises";
import type { Plugin } from "vite";
import { copyMaplibreWorkerPlugin } from "./vite.copyMaplibreWorker.ts";

// Tauri's `frontendDist` (desktop-etl/src-tauri/tauri.conf.json) requires
// an `index.html` at the root of the built output — it has no way to be
// told a different entry filename. The source file is named
// index.desktop.html (not index.html) only to avoid colliding with the
// normal shell's own shell/index.html in the same source directory; this
// plugin renames the built output back to index.html after the build.
// Found by actually running the built app on Windows (Tâche 6) — it
// failed at startup with "asset not found: index.html".
function renameDesktopEntryPlugin(): Plugin {
  return {
    name: "rename-desktop-entry-html",
    async closeBundle() {
      const outDir = resolve(__dirname, "dist-desktop");
      await rename(resolve(outDir, "index.desktop.html"), resolve(outDir, "index.html"));
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss(), copyMaplibreWorkerPlugin(), renameDesktopEntryPlugin()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist-desktop",
    rollupOptions: {
      input: resolve(__dirname, "index.desktop.html"),
    },
  },
});
