import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    // manifest: filet de taille (scripts/check-bundle-size.mjs, Task 9) —
    // calcule la charge JS/CSS initiale réelle depuis dist/.vite/manifest.json.
    manifest: true,
    rollupOptions: {
      output: {
        // Chunks de vendeur pour les bibliothèques les plus volumineuses
        // (Task 9, SP-60/GAP-68) : regroupées par famille de paquet plutôt
        // que dupliquées dans chaque chunk de route qui les consomme
        // (découpage par route, Task 8). Fonction plutôt qu'une liste
        // statique — pas de maintenance à chaque nouvelle dépendance.
        manualChunks(id) {
          if (id.includes("node_modules")) {
            // Écart trouvé par rapport au texte du plan (piège CLAUDE.md n°3,
            // "vérifier après un build" suivi à la lettre — et falsifié) :
            // regrouper @deck.gl/@loaders.gl dans ce même chunk fait basculer
            // sa charge en STATIQUE dans le graphe de l'entrée (mesuré :
            // entry.imports du manifeste Vite gagne le chunk fusionné dès
            // que l'un des deux est inclus), alors que maplibre-gl seul reste
            // dynamique. deck.gl/loaders.gl n'ont aujourd'hui qu'un seul
            // consommateur réel (MapView.tsx) — laissés au chunking
            // automatique de Rollup, déjà vérifié dynamique et sans
            // duplication (un seul point d'entrée). maplibre-gl, lui, a
            // plusieurs consommateurs dynamiques réels (MapView,
            // CatalogSpatialFilter, PipelinePreviewMap,
            // MapMeasureSketchToolbar) qui profitent du partage.
            if (id.includes("maplibre-gl")) return "vendor-map";
            if (id.includes("echarts")) return "vendor-echarts";
            if (id.includes("lit") || id.includes("@lit")) return "vendor-lit";
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    // e2e-oidc/** (SP-26/3.8) : suite Playwright séparée, mêmes raisons que
    // e2e/** — vitest ramasserait sinon *.spec.ts par son pattern d'include
    // par défaut et échouerait à la collecte (test.describe de Playwright,
    // pas de vitest).
    exclude: ["e2e/**", "e2e-oidc/**", "node_modules/**"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      exclude: [
        "e2e/**",
        "e2e-oidc/**",
        "node_modules/**",
        "src/api/generated/**",
        "**/*.test.{ts,tsx}",
      ],
    },
  },
});
