import { AuthProvider as OidcProvider } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { createContext, useRef } from "react";
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
      stateStore: new WebStorageStateStore({ store }),
    };
  }

  if (config.authMode === "mock") {
    return <MockAuthContext.Provider value={true}>{children}</MockAuthContext.Provider>;
  }
  return (
    <OidcProvider
      authority={config.oidcAuthority}
      client_id={config.oidcClientId}
      redirect_uri={config.oidcRedirectUri}
      response_type="code"
      scope="openid profile email"
      // In-memory store: nothing persisted to localStorage.
      userStore={storesRef.current.userStore}
      stateStore={storesRef.current.stateStore}
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
