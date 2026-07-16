import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:4173" },
  retries: process.env.CI ? 2 : 0,
  webServer: [
    {
      command: "npm run build && npm run preview -- --port 4173",
      url: "http://localhost:4173",
      reuseExistingServer: false,
      env: {
        VITE_AUTH_MODE: "mock",
        VITE_CORE_URL: "https://core.test",
        VITE_MARTIN_URL: "https://martin.test",
      },
    },
    {
      command: "node e2e/external-widget-server.mjs",
      url: "http://localhost:4174/widget.js",
      reuseExistingServer: false,
    },
  ],
});
