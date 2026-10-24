// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

// AUD-161 : la webview desktop ne doit parler qu'à elle-même et au sidecar loopback.
test("la CSP Tauri n'autorise aucune origine distante", () => {
  const conf = JSON.parse(readFileSync("../desktop-etl/src-tauri/tauri.conf.json", "utf8"));
  const csp: string = conf.app.security.csp;
  expect(csp).toContain("default-src 'self'");
  expect(csp).not.toMatch(/https?:\/\/(?!ipc\.localhost|127\.0\.0\.1)/);
  expect(csp).not.toContain("*.");
});
