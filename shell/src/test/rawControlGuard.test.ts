// SPDX-License-Identifier: Apache-2.0
// AUD-126/127 : cliquet sur les contrôles de formulaire natifs réécrits hors du kit
// (`ui/kit/{Input,NativeSelect,...}`). Le nombre par fichier ne peut ni croître ni apparaître
// dans un nouveau fichier ; une baisse oblige à abaisser la baseline (le cliquet ne recule pas).
// Un `<select>` s'écrit `NativeSelect`. `<input type=checkbox|radio|file|range|color>` et les
// contrôles dont le style est volontairement propre au composant restent comptés ici.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const f = join(dir, e);
    if (statSync(f).isDirectory()) walk(f, out);
    else if (/\.tsx$/.test(f) && !/\.test\.tsx$/.test(f)) out.push(f.replaceAll("\\", "/"));
  }
  return out;
}

function counts(): Record<string, number> {
  const out: Record<string, number> = {};
  for (const f of walk("src")) {
    if (f.startsWith("src/ui/kit/")) continue;
    const n = (readFileSync(f, "utf8").match(/<(select|input|textarea)(?=[\s>])/g) ?? []).length;
    if (n > 0) out[f] = n;
  }
  return out;
}

const BASELINE: Record<string, number> = JSON.parse(
  readFileSync("src/test/rawControlBaseline.json", "utf8"),
);

test("aucun contrôle natif nouveau hors du kit (select/input/textarea)", () => {
  const now = counts();
  const grown = Object.entries(now).filter(([f, n]) => n > (BASELINE[f] ?? 0));
  expect(grown, "contrôle natif ajouté : utiliser ui/kit (Input, NativeSelect…)").toEqual([]);
});

test("la baseline suit les migrations (cliquet : elle ne peut que baisser)", () => {
  const now = counts();
  const stale = Object.entries(BASELINE).filter(([f, n]) => (now[f] ?? 0) < n);
  expect(stale, "baseline périmée : abaisser/retirer ces entrées").toEqual([]);
});
