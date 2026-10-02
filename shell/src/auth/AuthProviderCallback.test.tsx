// SPDX-License-Identifier: Apache-2.0
// P07.02 : le callback Keycloak restaure la route demandée et nettoie code/state.
import { render } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AppConfig } from "../config";

let captured: { onSigninCallback?: (user?: unknown) => void } = {};
const signinRedirect = vi.fn();
vi.mock("react-oidc-context", () => ({
  AuthProvider: (props: {
    onSigninCallback?: (u?: unknown) => void;
    children: React.ReactNode;
  }) => {
    captured = props;
    return <>{props.children}</>;
  },
  useAuth: () => ({ user: { profile: { sub: "u1" } }, signinRedirect }),
}));

const { AuthProvider } = await import("./AuthProvider");

const config = {
  authMode: "oidc",
  oidcAuthority: "http://kc",
  oidcClientId: "c",
  oidcRedirectUri: "http://localhost/",
} as unknown as AppConfig;

it("onSigninCallback remplace l'URL de callback par le returnTo conservé", () => {
  render(
    <AuthProvider config={config}>
      <p>x</p>
    </AuthProvider>,
  );
  window.history.replaceState({}, "", "/?code=abc&state=def");
  const popstate = vi.fn();
  window.addEventListener("popstate", popstate);
  captured.onSigninCallback?.({ state: { returnTo: "/items/42?tab=a" } });
  expect(window.location.pathname + window.location.search).toBe("/items/42?tab=a");
  expect(popstate).toHaveBeenCalled();

  captured.onSigninCallback?.({ state: { returnTo: "//evil.com" } });
  expect(window.location.pathname).toBe("/");
  expect(window.location.search).toBe("");
  window.removeEventListener("popstate", popstate);
});
