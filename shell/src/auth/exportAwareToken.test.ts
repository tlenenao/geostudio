// SPDX-License-Identifier: Apache-2.0
import { buildExportAwareToken } from "./exportAwareToken";

// buildExportAwareToken reads `window.location.search` directly (see the
// comment on the function for why: App.tsx's AppShell sits above the
// BrowserRouter it renders, so no Router context is available where
// `getToken` is constructed). Exercise it against real
// `window.history.pushState` navigations rather than mocking
// `window.location`, since jsdom supports pushState natively and it is the
// same mechanism a real browser uses to change the URL without a full reload.
afterEach(() => {
  window.history.pushState({}, "", "/");
});

test("prefers the exportToken query param over the normal access token when present", () => {
  window.history.pushState({}, "", "/maps/1?exportToken=worker-token-abc");
  const getAccessToken = () => "oidc-session-token";

  const getToken = buildExportAwareToken(getAccessToken);

  expect(getToken()).toBe("worker-token-abc");
});

test("falls back to the normal access token when exportToken is absent", () => {
  window.history.pushState({}, "", "/maps/1");
  const getAccessToken = () => "oidc-session-token";

  const getToken = buildExportAwareToken(getAccessToken);

  expect(getToken()).toBe("oidc-session-token");
});
