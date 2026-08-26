import { defineConfig } from "@playwright/test";

// Suite séparée de playwright.config.ts (mock) : celle-ci suppose une
// stack docker compose déjà démarrée (postgis+keycloak+core+shell réels,
// CORE_AUTH_MODE=oidc) — pas de webServer local, pas de mock réseau
// (SP-26/3.8, I13 revue de projet 2026-08-20).
export default defineConfig({
  testDir: "./e2e-oidc",
  use: { baseURL: "http://localhost:8300" },
  retries: process.env.CI ? 2 : 0,
  timeout: 30_000,
});
