// SPDX-License-Identifier: Apache-2.0
// REV-285(b) : `h-8` réservé aux contextes denses documentés (convention CLAUDE.md 2026-09-01).
// REV-323 (lot C) : le garde couvre aussi les `.ts` (classes composées en code) et
// l'allowlist ne dispense plus un fichier entier mais UN fragment précis par fichier.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

const DENSE_ALLOWED: Record<string, string> = {
  "src/ui/kit/Button.tsx": 'sm: "h-8 px-3 text-xs"', // variante size="sm"
  "src/ui/kit/Avatar.tsx": "h-8 w-8", // pastille, pas un contrôle de formulaire
  "src/ui/button.tsx": 'sm: "h-8 px-3"', // primitive legacy
  "src/builder/widgets/indicator.tsx": 'className="h-8 w-full"', // conteneur de sparkline
};

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const f = join(dir, e);
    if (statSync(f).isDirectory()) walk(f, out);
    else if (/\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) && !f.endsWith(".d.ts")) out.push(f);
  }
  return out;
}

test("aucun h-8 hors des fragments denses documentés", () => {
  const offenders = walk("src").filter((f) => {
    const allowed = DENSE_ALLOWED[f.replaceAll("\\", "/")];
    const source = readFileSync(f, "utf8");
    return /\bh-8\b/.test(allowed ? source.replaceAll(allowed, "") : source);
  });
  expect(offenders).toEqual([]);
});

test("chaque dispense documente un fragment réellement présent (pas de dispense morte)", () => {
  const dead = Object.entries(DENSE_ALLOWED).filter(
    ([file, fragment]) => !readFileSync(file, "utf8").includes(fragment),
  );
  expect(dead).toEqual([]);
});
