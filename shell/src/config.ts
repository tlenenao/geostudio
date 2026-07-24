// SPDX-License-Identifier: Apache-2.0
export type AppConfig = {
  coreUrl: string;
  martinUrl: string;
  oidcAuthority: string;
  oidcClientId: string;
  oidcRedirectUri: string;
  authMode: "oidc" | "mock";
};

function mergeRuntimeEnv(
  env: Record<string, string | undefined>,
  runtimeEnv: Record<string, string | undefined> | undefined,
): Record<string, string | undefined> {
  if (!runtimeEnv) return env;
  const merged = { ...env };
  for (const [key, value] of Object.entries(runtimeEnv)) {
    // envsubst laisse "${VAR}" tel quel quand VAR n'était pas définie au
    // démarrage du conteneur (ou en dev, où /env-config.js n'existe pas et
    // ce paramètre vaut undefined de toute façon) — ne jamais laisser un
    // placeholder non substitué écraser une vraie valeur de build.
    if (value !== undefined && !value.startsWith("${")) {
      merged[key] = value;
    }
  }
  return merged;
}

export function loadConfig(
  env: Record<string, string | undefined>,
  runtimeEnv?: Record<string, string | undefined>,
): AppConfig {
  const merged = mergeRuntimeEnv(env, runtimeEnv);
  const authMode = merged.VITE_AUTH_MODE === "mock" ? "mock" : "oidc";

  const required: Record<string, string | undefined> = {
    VITE_CORE_URL: merged.VITE_CORE_URL,
  };
  if (authMode === "oidc") {
    required.VITE_OIDC_AUTHORITY = merged.VITE_OIDC_AUTHORITY;
    required.VITE_OIDC_CLIENT_ID = merged.VITE_OIDC_CLIENT_ID;
    required.VITE_OIDC_REDIRECT_URI = merged.VITE_OIDC_REDIRECT_URI;
  }

  const missing = Object.entries(required)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(`Missing required env vars: ${missing.join(", ")}`);
  }

  return {
    coreUrl: merged.VITE_CORE_URL!,
    martinUrl: merged.VITE_MARTIN_URL ?? "",
    oidcAuthority: merged.VITE_OIDC_AUTHORITY ?? "",
    oidcClientId: merged.VITE_OIDC_CLIENT_ID ?? "",
    oidcRedirectUri: merged.VITE_OIDC_REDIRECT_URI ?? "",
    authMode,
  };
}
