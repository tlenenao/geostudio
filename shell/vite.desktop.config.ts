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
import { copyMaplibreWorkerPlugin } from "./vite.copyMaplibreWorker.ts";

export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss(), copyMaplibreWorkerPlugin()],
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
