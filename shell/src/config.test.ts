// SPDX-License-Identifier: Apache-2.0
import { vi } from "vitest";
import { loadConfig } from "./config";
import { createBase } from "./api/base";
import { isHostedCollectionUrl } from "./map/hostedCoreUrl";

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

test("loadRuntimeConfig lit __GEOSTUDIO_ENV__ (P22.03)", async () => {
  const { loadRuntimeConfig } = await import("./config");
  (window as unknown as { __GEOSTUDIO_ENV__: Record<string, string> }).__GEOSTUDIO_ENV__ = {
    VITE_CORE_URL: "http://rt.test",
    VITE_AUTH_MODE: "mock",
  };
  try {
    expect(loadRuntimeConfig().coreUrl).toBe("http://rt.test");
  } finally {
    delete (window as unknown as { __GEOSTUDIO_ENV__?: unknown }).__GEOSTUDIO_ENV__;
  }
});

test("REV-300 M5 : un VITE_CORE_URL relatif sans « / » initial est refusé avec un message clair", () => {
  expect(() => loadConfig({ ...base, VITE_CORE_URL: "api" })).toThrow(/VITE_CORE_URL invalide/);
});

test("REV-272b : un VITE_CORE_URL relatif est résolu contre l'origine de la page", () => {
  expect(loadConfig({ ...base, VITE_CORE_URL: "/api" }).coreUrl).toBe(
    `${window.location.origin}/api`,
  );
  expect(loadConfig({ ...base, VITE_CORE_URL: "/api/" }).coreUrl).toBe(
    `${window.location.origin}/api`,
  );
  expect(loadConfig({ ...base, VITE_CORE_URL: "/" }).coreUrl).toBe(window.location.origin);
});

test("REV-272b : une URL absolue reste inchangée (runtime env compris)", () => {
  expect(loadConfig(base).coreUrl).toBe("https://core.test");
  expect(loadConfig(base, { VITE_CORE_URL: "https://prod.example/api" }).coreUrl).toBe(
    "https://prod.example/api",
  );
});

test("REV-272b : le client bâti sur un coreUrl relatif résolu garde le jeton sur les URL du cœur", async () => {
  const { coreUrl } = loadConfig({ ...base, VITE_CORE_URL: "/api" });
  const client = createBase({ coreUrl, getToken: () => "tok" });
  const tile = `${client.coreUrl}/collections/c/tiles/0/0/0.mvt`;
  expect(client.coreUrl).toBe(`${window.location.origin}/api/v1`);
  expect(isHostedCollectionUrl(tile, client.coreUrl)).toBe(true);
  const fetchSpy = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetchSpy);
  try {
    await client.fetchUrl(tile, { authenticated: true });
    expect((fetchSpy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
  } finally {
    vi.unstubAllGlobals();
  }
});
