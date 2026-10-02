// SPDX-License-Identifier: Apache-2.0
import { AuthProvider as OidcProvider, useAuth as useOidcAuth } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { createContext, useRef } from "react";
import type { AppConfig } from "../config";
import { setStorageUser } from "../lib/userStorage";
import { safeReturnTo } from "./returnTo";
import { enableMockAuth } from "./useAuth";

type ReturnState = { returnTo?: unknown } | undefined;

// P07.07/08 : publie l'id du compte AVANT le rendu des enfants (un
// useEffect arriverait après les initialiseurs d'état qui lisent
// localStorage). Écriture idempotente d'un module-level, sans effet visible.
function StorageUserSync({ children }: { children: React.ReactNode }) {
  setStorageUser(useOidcAuth().user?.profile.sub);
  return <>{children}</>;
}

// Mock context value mirrors the react-oidc-context User minimally; only used in tests/E2E.
export const MockAuthContext = createContext(true);

export function AuthProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: React.ReactNode;
}) {
  // Stabilize the in-memory stores so they are created exactly once per
  // AuthProvider instance. Constructing them inline in the render body would
  // recreate them on every render, causing react-oidc-context to reinitialize
  // its UserManager with a fresh (empty) store and lose in-flight tokens.
  const storesRef = useRef<{
    userStore: WebStorageStateStore;
    stateStore: WebStorageStateStore;
  } | null>(null);
  if (!storesRef.current) {
    const store = new InMemoryStore();
    storesRef.current = {
      userStore: new WebStorageStateStore({ store }),
      stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    };
  }

  if (config.authMode === "mock") {
    enableMockAuth();
    return <MockAuthContext.Provider value={true}>{children}</MockAuthContext.Provider>;
  }
  return (
    <OidcProvider
      authority={config.oidcAuthority}
      client_id={config.oidcClientId}
      redirect_uri={config.oidcRedirectUri}
      // Sans cette prop, oidc-client-ts n'envoie aucun
      // post_logout_redirect_uri à l'endpoint de déconnexion de Keycloak :
      // l'utilisateur reste bloqué sur la page "You are logged out" nue de
      // Keycloak au lieu de revenir sur le shell (trouvé par la suite E2E
      // OIDC réelle, SP-26/3.8 — le mode mock ne pouvait pas le révéler).
      // Réutilise la même URI déjà whitelistée côté Keycloak
      // (redirect_uri), enregistrée aussi comme post-logout redirect URI
      // valide sur le client geostudio-shell (deploy/keycloak/
      // geostudio-realm.json).
      post_logout_redirect_uri={config.oidcRedirectUri}
      response_type="code"
      scope="openid profile email"
      // In-memory store: nothing persisted to localStorage.
      userStore={storesRef.current.userStore}
      stateStore={storesRef.current.stateStore}
      // P07.02 : nettoie code/state de l'URL et restaure la route demandée.
      // Le popstate resynchronise le data router (module-level) sur la
      // nouvelle URL.
      onSigninCallback={(user) => {
        window.history.replaceState({}, "", safeReturnTo((user?.state as ReturnState)?.returnTo));
        window.dispatchEvent(new PopStateEvent("popstate"));
      }}
    >
      <StorageUserSync>{children}</StorageUserSync>
    </OidcProvider>
  );
}

// In-memory implementation of oidc-client-ts AsyncStorage interface.
// Adapted from brief: added length, clear(), and key(index) to satisfy the interface.
// Uses a Map so no data ever touches localStorage/sessionStorage.
class InMemoryStore {
  private data = new Map<string, string>();

  get length(): Promise<number> {
    return Promise.resolve(this.data.size);
  }

  async clear(): Promise<void> {
    this.data.clear();
  }

  async getItem(key: string): Promise<string | null> {
    return this.data.get(key) ?? null;
  }

  async key(index: number): Promise<string | null> {
    const keys = [...this.data.keys()];
    return keys[index] ?? null;
  }

  async removeItem(key: string): Promise<void> {
    this.data.delete(key);
  }

  async setItem(key: string, value: string): Promise<void> {
    this.data.set(key, value);
  }
}
