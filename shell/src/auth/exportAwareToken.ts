// SPDX-License-Identifier: Apache-2.0

// Prefers the `exportToken` query param over the normal OIDC/mock token when
// present. The Playwright export worker (Task 6, core/app/export/jobs.py)
// carries only this token, not a real Keycloak session — every API call it
// makes through the ItemClient must authenticate with it instead. Reads
// `window.location.search` directly (rather than react-router-dom's
// `useSearchParams`) because the caller (App.tsx's `AppShell`) sits above the
// `BrowserRouter` it renders, so no Router context is available at the point
// `getToken` is constructed; the export token, like the browser URL itself,
// doesn't change without a full navigation, so a plain read at call time is
// equivalent and needs no Router.
//
// Lives in its own module (rather than inline in App.tsx) so it can be unit
// tested without pulling in App.tsx's module-level side effects (env-var
// backed `loadConfig()` call, and the maplibre-gl-heavy `AppRoutes` import
// tree, both of which break under jsdom).
export function buildExportAwareToken(getAccessToken: () => string | undefined) {
  return () => {
    const exportToken = new URLSearchParams(window.location.search).get("exportToken");
    return exportToken ?? getAccessToken();
  };
}
