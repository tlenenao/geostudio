// SPDX-License-Identifier: Apache-2.0
import {
  buildExportAwareToken,
  EXPORT_TOKEN_STORAGE_KEY,
  readExportToken,
} from "./exportAwareToken";

// Exercised against real `window.history.pushState` navigations (jsdom supports
// it natively) rather than mocking `window.location`.
afterEach(() => {
  window.sessionStorage.clear();
  window.history.pushState({}, "", "/");
});

test("uses the worker-injected token only in export render mode", () => {
  window.sessionStorage.setItem(EXPORT_TOKEN_STORAGE_KEY, "tok");
  window.history.pushState({}, "", "/maps/x?exportRender=1");
  expect(buildExportAwareToken(() => "oidc")()).toBe("tok");
});

test("ignores an exportToken query param (no login-CSRF through a link)", () => {
  window.history.pushState({}, "", "/maps/x?exportToken=attacker&exportRender=1");
  expect(readExportToken()).toBeNull();
  expect(buildExportAwareToken(() => "oidc")()).toBe("oidc");
});

test("ignores the stored token outside export render mode", () => {
  window.sessionStorage.setItem(EXPORT_TOKEN_STORAGE_KEY, "tok");
  window.history.pushState({}, "", "/maps/x");
  expect(buildExportAwareToken(() => "oidc")()).toBe("oidc");
});
