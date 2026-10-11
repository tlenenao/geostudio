// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext } from "react";

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

// Fourni par AuthProvider (état anonyme) ou OidcAuthProvider (chargé à la demande).
export const AuthContext = createContext<AuthState | null>(null);

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
  const ctx = useContext(AuthContext);
  if (mockMode) return MOCK_STATE;
  if (!ctx) throw new Error("useAuth must be called under <AuthProvider>");
  return ctx;
}
