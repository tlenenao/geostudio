import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:4173" },
  retries: process.env.CI ? 2 : 0,
  // Tâche 36 (SP-C6, D16) : la suite existante n'avait aucun tableau
  // `projects` (un seul projet implicite, chromium desktop). On l'explicite
  // ici pour ajouter un second projet mobile tactile SANS dupliquer
  // l'exécution des 57+ specs existantes sous ce second projet : "chromium"
  // reprend leur périmètre à l'identique (testIgnore exclut juste le
  // nouveau spec tactile, qui a besoin de `hasTouch` pour `locator.tap()`),
  // "mobile-touch" ne matche que ce nouveau spec.
  projects: [
    {
      name: "chromium",
      testIgnore: /map-touch\.spec\.ts/,
    },
    {
      name: "mobile-touch",
      // `devices["iPhone 13"]` pointe par défaut vers webkit
      // (`defaultBrowserType`) — non installé ici ni en CI (`ci.yml` ne fait
      // `playwright install --with-deps` que pour chromium). On garde son
      // émulation tactile/viewport mais on force chromium, seul navigateur
      // disponible.
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium", hasTouch: true },
      testMatch: /map-touch\.spec\.ts/,
    },
  ],
  webServer: [
    {
      command: "npm run build && npm run preview -- --port 4173",
      url: "http://localhost:4173",
      reuseExistingServer: false,
      env: {
        VITE_AUTH_MODE: "mock",
        VITE_CORE_URL: "https://core.test",
      },
    },
    {
      command: "node e2e/external-widget-server.mjs",
      url: "http://localhost:4174/widget.js",
      reuseExistingServer: false,
    },
  ],
});
