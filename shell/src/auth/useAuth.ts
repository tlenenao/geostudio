import { useAuth as useOidcAuth } from "react-oidc-context";

export type AuthState = {
  isLoading: boolean;
  isAuthenticated: boolean;
  username: string | null;
  getAccessToken: () => string | undefined;
  signIn: () => void;
  signOut: () => void;
};

export function useAuth(): AuthState {
  const oidc = useOidcAuth();
  return {
    isLoading: oidc.isLoading,
    isAuthenticated: oidc.isAuthenticated,
    username: (oidc.user?.profile.preferred_username as string) ?? null,
    getAccessToken: () => oidc.user?.access_token,
    signIn: () => void oidc.signinRedirect(),
    signOut: () => void oidc.signoutRedirect(),
  };
}
