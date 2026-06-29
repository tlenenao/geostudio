import { AuthProvider as OidcProvider } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { createContext } from "react";
import type { AppConfig } from "../config";

// Mock context value mirrors the react-oidc-context User minimally; only used in tests/E2E.
export const MockAuthContext = createContext(true);

export function AuthProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: React.ReactNode;
}) {
  if (config.authMode === "mock") {
    return <MockAuthContext.Provider value={true}>{children}</MockAuthContext.Provider>;
  }
  const store = new InMemoryStore();
  return (
    <OidcProvider
      authority={config.oidcAuthority}
      client_id={config.oidcClientId}
      redirect_uri={config.oidcRedirectUri}
      response_type="code"
      scope="openid profile email"
      // In-memory store: nothing persisted to localStorage.
      userStore={new WebStorageStateStore({ store })}
      stateStore={new WebStorageStateStore({ store })}
    >
      {children}
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
