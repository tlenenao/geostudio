// SPDX-License-Identifier: Apache-2.0
export type AppConfig = {
  coreUrl: string;
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
    // envsubst rend une variable de la whitelist non définie au démarrage du
    // conteneur par une chaîne vide (pas par le texte "${VAR}" — ça,
    // seule une clé jamais passée à envsubst peut le laisser tel quel).
    // Dans les deux cas, ne jamais laisser cette non-valeur écraser une
    // vraie valeur de build.
    if (value !== undefined && value !== "" && !value.startsWith("${")) {
      merged[key] = value;
    }
  }
  return merged;
}

// REV-272b : `VITE_CORE_URL=/api` (cœur servi sous le même hôte que le shell,
// derrière un reverse-proxy) est une configuration légitime. Toute la chaîne
// aval (`new URL(coreUrl)` dans client/hostedCoreUrl/tuiles) exige une URL
// absolue : on la résout ici, une seule fois, contre l'origine de la page.
export function resolveCoreUrl(value: string): string {
  if (!value.startsWith("/")) return value;
  return new URL(value, window.location.origin).href.replace(/\/+$/, "");
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
    coreUrl: resolveCoreUrl(merged.VITE_CORE_URL!),
    oidcAuthority: merged.VITE_OIDC_AUTHORITY ?? "",
    oidcClientId: merged.VITE_OIDC_CLIENT_ID ?? "",
    oidcRedirectUri: merged.VITE_OIDC_REDIRECT_URI ?? "",
    authMode,
  };
}

// P22.03 : lecture unique de l'environnement (build Vite + injection runtime
// `window.__GEOSTUDIO_ENV__`), partagée par App.tsx et EmbedPage.tsx.
export function loadRuntimeConfig(): AppConfig {
  return loadConfig(
    import.meta.env as unknown as Record<string, string | undefined>,
    (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
      .__GEOSTUDIO_ENV__,
  );
}
