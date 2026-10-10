// SPDX-License-Identifier: Apache-2.0
// REV-285(b) : `h-8` réservé aux contextes denses documentés (convention CLAUDE.md 2026-09-01).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

const DENSE_ALLOWED = new Set([
  "src/ui/kit/Button.tsx", // variante size="sm"
  "src/ui/kit/Avatar.tsx", // pastille, pas un contrôle de formulaire
  "src/ui/button.tsx", // primitive legacy
  "src/builder/widgets/indicator.tsx", // conteneur de sparkline, pas un contrôle
]);

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const f = join(dir, e);
    if (statSync(f).isDirectory()) walk(f, out);
    else if (f.endsWith(".tsx") && !f.endsWith(".test.tsx")) out.push(f);
  }
  return out;
}

test("aucun h-8 hors contextes denses documentés", () => {
  const offenders = walk("src")
    .filter((f) => !DENSE_ALLOWED.has(f.replaceAll("\\", "/")))
    .filter((f) => /\bh-8\b/.test(readFileSync(f, "utf8")));
  expect(offenders).toEqual([]);
});
