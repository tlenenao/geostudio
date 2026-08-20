// SPDX-License-Identifier: Apache-2.0
// Jeton d'audience MCP distincte pour le copilote (SP-20) — obtenu par un
// appel direct au endpoint de token OIDC (grant_type=refresh_token) avec
// le scope geostudio-mcp-audience (provisionné Task 1), plutôt que via
// oidc.signinSilent(). signinSilent() a été abandonné après investigation
// (revue finale de branche) : sur la branche refresh-token de
// oidc-client-ts (systématiquement empruntée ici, geostudio-shell étant
// un client public qui reçoit toujours un refresh token), la librairie ne
// transmet PAS le paramètre scope au fournisseur — le jeton obtenu
// n'aurait donc jamais l'audience geostudio-mcp. L'appel direct évite
// aussi de remplacer l'utilisateur OIDC stocké de la session shell
// (signinSilent() écrase le User stocké via storeUser(), ce que cet appel
// ne fait jamais). Jeton en mémoire uniquement (useRef), jamais
// localStorage — même garantie que le jeton REST normal (cf.
// AuthProvider.tsx, InMemoryStore). Re-fetché automatiquement à
// l'approche de l'expiration (buffer 30s) plutôt que mis en cache
// indéfiniment.
import { useCallback, useRef } from "react";
import { useAuth as useOidcAuth } from "react-oidc-context";
import { isMockMode } from "../../auth/useAuth";

const MCP_SCOPE = "openid profile email geostudio-mcp-audience";
const EXPIRY_BUFFER_MS = 30_000;

type CachedToken = { accessToken: string; expiresAt: number };

export function useMcpToken(): () => Promise<string> {
  const cachedRef = useRef<CachedToken | null>(null);

  if (isMockMode()) {
    // mockMode est un drapeau au niveau module, fixé une fois avant tout
    // rendu (enableMockAuth() dans AuthProvider) — jamais togglé en cours
    // de vie de l'app, donc ce retour anticipé avant l'appel conditionnel
    // ci-dessous respecte quand même les rules-of-hooks en pratique, même
    // patron que useAuth.ts.
    // eslint-disable-next-line react-hooks/rules-of-hooks
    return useCallback(async () => "mock-mcp-token", []);
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
  const oidc = useOidcAuth();
  return useCallback(async () => {
    const cached = cachedRef.current;
    if (cached && Date.now() < cached.expiresAt) return cached.accessToken;

    const refreshToken = oidc.user?.refresh_token;
    if (!refreshToken) {
      throw new Error("Impossible d'obtenir un jeton MCP (pas de refresh token disponible).");
    }
    const response = await fetch(`${oidc.settings.authority}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        refresh_token: refreshToken,
        client_id: oidc.settings.client_id,
        scope: MCP_SCOPE,
      }),
    });
    if (!response.ok) {
      throw new Error("Impossible d'obtenir un jeton MCP (le serveur d'autorisation a refusé la demande).");
    }
    const body = (await response.json()) as { access_token?: string; expires_in?: number };
    if (!body.access_token) {
      throw new Error("Impossible d'obtenir un jeton MCP (réponse sans access_token).");
    }
    const expiresInMs = (body.expires_in ?? 60) * 1000;
    cachedRef.current = {
      accessToken: body.access_token,
      expiresAt: Date.now() + expiresInMs - EXPIRY_BUFFER_MS,
    };
    return body.access_token;
  }, [oidc]);
}
