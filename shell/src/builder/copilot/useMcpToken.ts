// SPDX-License-Identifier: Apache-2.0
// Jeton d'audience MCP distincte pour le copilote (SP-20) — obtenu via un
// second signinSilent() demandant le client-scope optionnel
// geostudio-mcp-audience (déjà provisionné dans le realm, Task 1), jamais
// via un paramètre resource ni token-exchange. Contourne délibérément le
// useAuth() de l'app (../../auth/useAuth), qui n'expose pas signinSilent —
// importe react-oidc-context directement, comme AuthProvider.tsx le fait
// déjà pour construire son propre <AuthProvider>. Le jeton ne vit qu'en
// mémoire (état React), jamais localStorage — même garantie que le jeton
// REST normal (cf. AuthProvider.tsx, InMemoryStore).
import { useCallback, useRef } from "react";
import { useAuth as useOidcAuth } from "react-oidc-context";
import { isMockMode } from "../../auth/useAuth";

const MCP_SCOPE = "openid profile email geostudio-mcp-audience";

export function useMcpToken(): () => Promise<string> {
  const cachedRef = useRef<string | null>(null);

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
    if (cachedRef.current) return cachedRef.current;
    const user = await oidc.signinSilent({ scope: MCP_SCOPE });
    if (!user?.access_token) {
      throw new Error("Impossible d'obtenir un jeton MCP (signinSilent a échoué).");
    }
    cachedRef.current = user.access_token;
    return user.access_token;
  }, [oidc]);
}
