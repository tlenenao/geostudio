// SPDX-License-Identifier: Apache-2.0

// The Playwright export worker (core/app/export/jobs.py) carries only an export
// token, not a real Keycloak session — every API call it makes through the
// ItemClient must authenticate with it instead.
//
// AUD-024 : the worker injects its token into sessionStorage (Playwright
// add_init_script, before any page script) ; it is never read from the URL,
// otherwise a crafted `?exportToken=` link would make the victim's session act
// under the attacker's account (login-CSRF). It is honoured only in export
// render mode (`?exportRender=1`).
//
// Reads `window.location.search` directly (rather than react-router-dom's
// `useSearchParams`) because the caller (App.tsx's `AppShell`) sits above the
// router it renders. Lives in its own module so it can be unit tested without
// pulling in App.tsx's module-level side effects.
export const EXPORT_TOKEN_STORAGE_KEY = "gs_export_token";

export function readExportToken(): string | null {
  if (new URLSearchParams(window.location.search).get("exportRender") !== "1") return null;
  try {
    return window.sessionStorage.getItem(EXPORT_TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function buildExportAwareToken(getAccessToken: () => string | undefined) {
  return () => readExportToken() ?? getAccessToken();
}
