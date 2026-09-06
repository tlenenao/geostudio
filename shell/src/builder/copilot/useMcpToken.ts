// SPDX-License-Identifier: Apache-2.0
// Jeton d'audience MCP distincte pour le copilote (SP-20) — obtenu via un
// second signinSilent({scope, forceIframeAuth: true}) demandant le
// client-scope optionnel geostudio-mcp-audience (provisionné Task 1).
//
// Historique (revue finale de branche, 2 tentatives) :
// 1. signinSilent({scope}) seul — abandonné : oidc-client-ts emprunte
//    systématiquement sa branche refresh-token ici (geostudio-shell
//    reçoit toujours un refresh token), qui ne transmet PAS `scope` au
//    fournisseur.
// 2. Appel direct au endpoint de token (grant_type=refresh_token) —
//    abandonné après vérification empirique contre un vrai Keycloak :
//    ce realm Keycloak 24 ne réapplique JAMAIS le mapper d'audience
//    personnalisé de geostudio-mcp-audience sur un grant refresh_token,
//    quel que soit le scope demandé (testé : up-scope, re-demande à
//    l'identique, scope par défaut vs optionnel — aucune combinaison ne
//    fonctionne). Seul le grant initial (authorization_code en usage
//    réel) produit l'audience geostudio-mcp.
// 3. (Ici) signinSilent({scope, forceIframeAuth: true}) — force
//    oidc-client-ts sur sa branche iframe silencieuse (un vrai
//    authorization_code frais via prompt=none), qui ne passe jamais par
//    le chemin refresh-token défaillant. Vérifié EN BOUT EN BOUT contre
//    un vrai navigateur+Keycloak 24+Traefik (REV-003, 2026-09) : même
//    avec `X-Frame-Options: DENY` forcé sur /auth (middleware
//    security-headers), signinSilent réussit sans accroc — prompt=none
//    ne rend jamais de HTML dans l'iframe (uniquement une redirection,
//    code ou erreur), et X-Frame-Options ne bloque que le RENDU d'un
//    document dans une frame, jamais le suivi d'une redirection au
//    travers. Aucun risque résiduel réel sur ce point précis.
//
// Contourne délibérément le useAuth() de l'app (../../auth/useAuth), qui
// n'expose pas signinSilent — importe react-oidc-context directement,
// comme AuthProvider.tsx le fait déjà pour construire son propre
// <AuthProvider>. Le jeton ne vit qu'en mémoire (état React), jamais
// localStorage — même garantie que le jeton REST normal (cf.
// AuthProvider.tsx, InMemoryStore). Mis en cache avec suivi
// d'expiration (buffer 30s) — jamais mis en cache indéfiniment.
//
// Effet de bord accepté (M4, revue finale de branche) : signinSilent()
// remplace l'utilisateur OIDC stocké de toute la session shell —
// inoffensif sur le realm de ce dépôt (mapper d'audience geostudio-core
// au niveau client, pas par scope), documenté comme suivi non bloquant.
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
  // Même garde que ci-dessus : ce useCallback n'est, comme useOidcAuth(),
  // atteignable que sur la branche non-mock — couverture manquante avant
  // l'activation réelle d'eslint sur ce fichier (SP-22 Task 3), même
  // justification que le disable précédent.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useCallback(async () => {
    const cached = cachedRef.current;
    if (cached && Date.now() < cached.expiresAt) return cached.accessToken;

    const user = await oidc.signinSilent({ scope: MCP_SCOPE, forceIframeAuth: true });
    if (!user?.access_token) {
      throw new Error("Impossible d'obtenir un jeton MCP (signinSilent a échoué).");
    }
    const expiresInMs = (user.expires_in ?? 60) * 1000;
    cachedRef.current = {
      accessToken: user.access_token,
      expiresAt: Date.now() + expiresInMs - EXPIRY_BUFFER_MS,
    };
    return user.access_token;
  }, [oidc]);
}
