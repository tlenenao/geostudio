// SPDX-License-Identifier: Apache-2.0
import { createContext, lazy, Suspense, useState } from "react";
import type { AppConfig } from "../config";
import { AuthContext, enableMockAuth, type AuthState } from "./useAuth";

// REV-267 : oidc-client-ts + react-oidc-context (~20 Ko gzip) ne sont chargés
// qu'à la demande — jamais pour un visiteur anonyme de /public.
const OidcAuthProvider = lazy(() => import("./OidcAuthProvider"));

// Mock context value mirrors the react-oidc-context User minimally; only used in tests/E2E.
export const MockAuthContext = createContext(true);

// Le magasin utilisateur OIDC est en mémoire : un chargement frais est
// toujours anonyme. /public sans retour de callback (code/state) n'a donc
// aucune session à restaurer.
export function isAnonymousLanding(loc: Pick<Location, "pathname" | "search">): boolean {
  const q = new URLSearchParams(loc.search);
  return (
    (loc.pathname === "/public" || loc.pathname.startsWith("/public/")) &&
    !q.has("code") &&
    !q.has("state") &&
    !q.has("error")
  );
}

export function AuthProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: React.ReactNode;
}) {
  const [needOidc, setNeedOidc] = useState(
    () => config.authMode !== "mock" && !isAnonymousLanding(window.location),
  );
  const [signInOnMount, setSignInOnMount] = useState(false);

  if (config.authMode === "mock") {
    enableMockAuth();
    return <MockAuthContext.Provider value={true}>{children}</MockAuthContext.Provider>;
  }
  if (!needOidc) {
    const anonymous: AuthState = {
      isLoading: false,
      isAuthenticated: false,
      username: null,
      error: null,
      getAccessToken: () => undefined,
      signIn: () => {
        setSignInOnMount(true);
        setNeedOidc(true);
      },
      signOut: () => {},
    };
    return <AuthContext.Provider value={anonymous}>{children}</AuthContext.Provider>;
  }
  return (
    <Suspense fallback={null}>
      <OidcAuthProvider config={config} signInOnMount={signInOnMount}>
        {children}
      </OidcAuthProvider>
    </Suspense>
  );
}
