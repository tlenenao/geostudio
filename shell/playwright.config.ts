import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:4173" },
  webServer: {
    command: "npm run build && npm run preview -- --port 4173",
    url: "http://localhost:4173",
    reuseExistingServer: false,
    env: {
      VITE_AUTH_MODE: "mock",
      VITE_GEONODE_URL: "https://geonode.test",
      VITE_BUILDER_URL: "https://builder.test",
      VITE_MARTIN_URL: "https://martin.test",
      VITE_FEATURESERV_URL: "https://featureserv.test",
    },
  },
});
