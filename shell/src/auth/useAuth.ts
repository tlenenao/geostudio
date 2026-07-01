import { useAuth as useOidcAuth } from "react-oidc-context";

export type AuthState = {
  isLoading: boolean;
  isAuthenticated: boolean;
  username: string | null;
  error: string | null;
  getAccessToken: () => string | undefined;
  signIn: () => void;
  signOut: () => void;
};

let mockMode = false;
export function enableMockAuth() {
  mockMode = true;
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
    signIn: () => void oidc.signinRedirect(),
    signOut: () => void oidc.signoutRedirect(),
  };
}
