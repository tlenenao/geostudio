// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test, vi } from "vitest";
import { getWidget } from "../registry";
import { registerExampleWidgets } from ".";

afterEach(() => vi.unstubAllEnvs());

// L'ordre compte : le registre est global au module, un widget enregistré y reste.
test("les widgets d'exemple ne sont pas enregistrés hors mode mock (P10.06)", () => {
  vi.stubEnv("VITE_AUTH_MODE", "oidc");
  registerExampleWidgets();
  expect(getWidget("example.counter")).toBeUndefined();
});

test("ils sont enregistrés en mode mock (dev/E2E)", () => {
  vi.stubEnv("VITE_AUTH_MODE", "mock");
  registerExampleWidgets();
  expect(getWidget("example.counter")).toBeDefined();
});
