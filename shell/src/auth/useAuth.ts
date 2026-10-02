// SPDX-License-Identifier: Apache-2.0
import { useAuth as useOidcAuth } from "react-oidc-context";
import { currentReturnTo } from "./returnTo";
import { purgeLocalHistories } from "../lib/userStorage";

export type AuthState = {
  isLoading: boolean;
  isAuthenticated: boolean;
  username: string | null;
  error: string | null;
  getAccessToken: () => string | undefined;
  signIn: () => void;
  signOut: () => void;
  // Renouvellement silencieux du jeton REST (P07.06) : renvoie le nouveau
  // jeton, ou undefined si la session ne peut plus être renouvelée.
  renewToken?: () => Promise<string | undefined>;
};

let mockMode = false;
export function enableMockAuth() {
  mockMode = true;
}
export function isMockMode(): boolean {
  return mockMode;
}

const MOCK_STATE: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "mockuser",
  error: null,
  getAccessToken: () => "mock-token",
  signIn: () => {},
  signOut: () => {},
};

export function useAuth(): AuthState {
  if (mockMode) return MOCK_STATE;
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const oidc = useOidcAuth();
  return {
    isLoading: oidc.isLoading,
    isAuthenticated: oidc.isAuthenticated,
    username: (oidc.user?.profile.preferred_username as string) ?? null,
    error: oidc.error ? oidc.error.message : null,
    getAccessToken: () => oidc.user?.access_token,
    // returnTo (P07.02) : la destination demandée survit à l'aller-retour
    // Keycloak (état OIDC conservé en sessionStorage, cf. AuthProvider).
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
}
