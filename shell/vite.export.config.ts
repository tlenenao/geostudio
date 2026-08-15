// SPDX-License-Identifier: Apache-2.0
// Config Vite séparée de vite.config.ts (config combinée Vite+Vitest) : ce
// build ne doit jamais dépendre de la config de test, et produit un
// artefact générique (pas lié à une app précise) rebâti une seule fois à
// l'image, jamais par export (SP-18a, plan §Architecture).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { resolve } from "node:path";

export default defineConfig({
  // Relative base: the bundle is unzipped under an arbitrary sub-path
  // (GitHub Pages project site, S3 prefix, …), never guaranteed to be
  // served from the domain root — "/" would make every asset URL absolute
  // from the host root and 404 anywhere else (SP-18a review, C1).
  base: "./",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist-export",
    rollupOptions: {
      input: resolve(__dirname, "index.export.html"),
    },
  },
});
