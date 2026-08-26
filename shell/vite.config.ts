import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
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
