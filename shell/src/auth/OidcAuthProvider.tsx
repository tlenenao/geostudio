// SPDX-License-Identifier: Apache-2.0
// Seul module (avec useMcpToken) à importer react-oidc-context/oidc-client-ts :
// chargé à la demande par AuthProvider (REV-267), jamais pour un visiteur
// anonyme de /public.
import { AuthProvider as OidcProvider, useAuth as useOidcAuth } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { useEffect, useRef } from "react";
import type { AppConfig } from "../config";
import { getLocale, hasLocalePreference, setLocalePreference } from "../i18n";
import { purgeLocalHistories, setStorageUser } from "../lib/userStorage";
import { currentReturnTo, safeReturnTo } from "./returnTo";
import { AuthContext, type AuthState } from "./useAuth";

type ReturnState = { returnTo?: unknown } | undefined;

// P07.07/08 : publie l'id du compte AVANT le rendu des enfants (un
// useEffect arriverait après les initialiseurs d'état qui lisent
// localStorage). Écriture idempotente d'un module-level, sans effet visible.
function StorageUserSync({ children }: { children: React.ReactNode }) {
  setStorageUser(useOidcAuth().user?.profile.sub);
  return <>{children}</>;
}

// Passerelle react-oidc-context -> AuthState consommé par useAuth().
function OidcBridge({
  signInOnMount,
  children,
}: {
  signInOnMount: boolean;
  children: React.ReactNode;
}) {
  const oidc = useOidcAuth();
  // AUD-019 : le claim OIDC `locale` amorce la langue au 1er login (jamais contre un choix explicite).
  const claimLocale = String(oidc.user?.profile.locale ?? "").slice(0, 2);
  useEffect(() => {
    if (hasLocalePreference() || (claimLocale !== "fr" && claimLocale !== "en")) return;
    if (claimLocale !== getLocale()) setLocalePreference(claimLocale);
  }, [claimLocale]);
  const state: AuthState = {
    isLoading: oidc.isLoading,
    isAuthenticated: oidc.isAuthenticated,
    username: (oidc.user?.profile.preferred_username as string) ?? null,
    error: oidc.error ? oidc.error.message : null,
    getAccessToken: () => oidc.user?.access_token,
    // returnTo (P07.02) : la destination demandée survit à l'aller-retour
    // Keycloak (état OIDC conservé en sessionStorage).
    signIn: () =>
      void oidc.signinRedirect({ state: { returnTo: currentReturnTo(window.location) } }),
    signOut: () => {
      purgeLocalHistories();
      void oidc.signoutRedirect();
    },
    renewToken: async () => {
      try {
        return (await oidc.signinSilent())?.access_token ?? undefined;
      } catch {
        return undefined;
      }
    },
  };
  // Connexion demandée depuis l'état anonyme (ex. /public) : le fournisseur
  // vient d'être chargé, on enchaîne sur la redirection.
  const done = useRef(false);
  useEffect(() => {
    if (signInOnMount && !done.current && !oidc.isLoading && !oidc.isAuthenticated) {
      done.current = true;
      state.signIn();
    }
  });
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}

export default function OidcAuthProvider({
  config,
  signInOnMount = false,
  children,
}: {
  config: AppConfig;
  signInOnMount?: boolean;
  children: React.ReactNode;
}) {
  // Stabilize the in-memory stores so they are created exactly once per
  // provider instance. Constructing them inline in the render body would
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

  return (
    <OidcProvider
      authority={config.oidcAuthority}
      client_id={config.oidcClientId}
      redirect_uri={config.oidcRedirectUri}
      // Sans cette prop, oidc-client-ts n'envoie aucun
      // post_logout_redirect_uri à l'endpoint de déconnexion de Keycloak :
      // l'utilisateur reste bloqué sur la page "You are logged out" nue de
      // Keycloak au lieu de revenir sur le shell (trouvé par la suite E2E
      // OIDC réelle, SP-26/3.8). Même URI que redirect_uri, déjà whitelistée
      // (deploy/keycloak/geostudio-realm.json).
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
      <StorageUserSync>
        <OidcBridge signInOnMount={signInOnMount}>{children}</OidcBridge>
      </StorageUserSync>
    </OidcProvider>
  );
}

// In-memory implementation of oidc-client-ts AsyncStorage interface.
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
