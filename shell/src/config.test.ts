// SPDX-License-Identifier: Apache-2.0
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

test("runtime env overrides build-time env when present and substituted", () => {
  const cfg = loadConfig(base, {
    VITE_CORE_URL: "https://prod.example",
    VITE_OIDC_AUTHORITY: "https://prod.example/auth/realms/geostudio",
  });
  expect(cfg.coreUrl).toBe("https://prod.example");
  expect(cfg.oidcAuthority).toBe("https://prod.example/auth/realms/geostudio");
  // Non fourni par le runtime env : repli sur la valeur build-time.
  expect(cfg.oidcClientId).toBe("shell");
});

test("runtime env with un-substituted envsubst placeholder falls back to build-time", () => {
  const cfg = loadConfig(base, { VITE_CORE_URL: "${VITE_CORE_URL}" });
  expect(cfg.coreUrl).toBe("https://core.test");
});

test("runtime env with empty string (envsubst on an unset whitelisted var) falls back to build-time", () => {
  const cfg = loadConfig(base, { VITE_CORE_URL: "" });
  expect(cfg.coreUrl).toBe("https://core.test");
});

test("absent runtime env behaves exactly like before (undefined second arg)", () => {
  const cfg = loadConfig(base);
  expect(cfg.coreUrl).toBe("https://core.test");
});
