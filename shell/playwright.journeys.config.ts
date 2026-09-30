import { defineConfig } from "@playwright/test";

// Parcours d'audit sur STACK RÉELLE (spec 2026-09-29 §5) : pas de webServer,
// pas de mock réseau — la stack docker compose doit tourner
// (scripts/audit/stack-reset.sh reset --auth mock|oidc). Un seul worker : les
// agents partagent l'unique tenant `default`, l'isolation vient du reset de
// base entre agents, pas du parallélisme.
export default defineConfig({
  testDir: "./e2e/journeys",
  use: {
    baseURL: process.env.SHELL_URL ?? "http://localhost:8300",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Le shell (:8300) appelle le cœur (:8200) en cross-origin, or le cœur n'a
    // aucun middleware CORS pour l'API générale (le déploiement réel passe par
    // Traefik en same-origin sous /api, indisponible sur localhost). On coupe
    // donc la sécurité web de Chromium pour ces parcours d'audit, plutôt que
    // de simuler du CORS par page.route.
    launchOptions: { args: ["--disable-web-security"] },
  },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["json", { outputFile: "test-results/journeys.json" }]],
});
