import { loadConfig } from "./config";

const base = {
  VITE_CORE_URL: "https://core.test",
  VITE_OIDC_AUTHORITY: "https://kc.test/realms/gis",
  VITE_OIDC_CLIENT_ID: "shell",
  VITE_OIDC_REDIRECT_URI: "https://app.test/callback",
};

test("loads a full oidc config", () => {
  const cfg = loadConfig(base);
  expect(cfg.coreUrl).toBe("https://core.test");
  expect(cfg.authMode).toBe("oidc");
  expect(cfg.oidcClientId).toBe("shell");
});

test("throws listing all missing required vars in oidc mode", () => {
  expect(() => loadConfig({})).toThrow(/VITE_CORE_URL/);
  expect(() => loadConfig({})).toThrow(/VITE_OIDC_AUTHORITY/);
});

test("mock mode does not require oidc vars", () => {
  const cfg = loadConfig({
    VITE_CORE_URL: "https://core.test",
    VITE_AUTH_MODE: "mock",
  });
  expect(cfg.authMode).toBe("mock");
  expect(cfg.oidcAuthority).toBe("");
});
