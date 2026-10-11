// SPDX-License-Identifier: Apache-2.0
// REV-267 : nginx compresse en niveau 1 par défaut, ce qui gonfle index.js d'environ 15 % et
// coûte un aller-retour TCP (slow start) sur le chemin critique de /public.
import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it("nginx.conf compresse les assets en gzip niveau >= 5", () => {
  const conf = readFileSync("nginx.conf", "utf8");
  const m = conf.match(/^\s*gzip_comp_level\s+(\d+);/m);
  expect(m, "gzip_comp_level absent de nginx.conf").not.toBeNull();
  expect(Number(m![1])).toBeGreaterThanOrEqual(5);
});
