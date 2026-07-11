export type AppConfig = {
  coreUrl: string;
  martinUrl: string;
  oidcAuthority: string;
  oidcClientId: string;
  oidcRedirectUri: string;
  authMode: "oidc" | "mock";
};

export function loadConfig(env: Record<string, string | undefined>): AppConfig {
  const authMode = env.VITE_AUTH_MODE === "mock" ? "mock" : "oidc";

  const required: Record<string, string | undefined> = {
    VITE_CORE_URL: env.VITE_CORE_URL,
  };
  if (authMode === "oidc") {
    required.VITE_OIDC_AUTHORITY = env.VITE_OIDC_AUTHORITY;
    required.VITE_OIDC_CLIENT_ID = env.VITE_OIDC_CLIENT_ID;
    required.VITE_OIDC_REDIRECT_URI = env.VITE_OIDC_REDIRECT_URI;
  }

  const missing = Object.entries(required)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(`Missing required env vars: ${missing.join(", ")}`);
  }

  return {
    coreUrl: env.VITE_CORE_URL!,
    martinUrl: env.VITE_MARTIN_URL ?? "",
    oidcAuthority: env.VITE_OIDC_AUTHORITY ?? "",
    oidcClientId: env.VITE_OIDC_CLIENT_ID ?? "",
    oidcRedirectUri: env.VITE_OIDC_REDIRECT_URI ?? "",
    authMode,
  };
}
