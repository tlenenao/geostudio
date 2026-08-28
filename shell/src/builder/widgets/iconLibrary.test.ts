// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test, vi } from "vitest";
import { installImageDecodeStub } from "../../test/imageDecodeStub";
import { decodeIconImage, LUCIDE_ICONS, rasterizeLucideIcon } from "./iconLibrary";
import { LUCIDE_ICON_SVGS } from "./lucideIconSvgs.generated";

// `installImageDecodeStub` mute `globalThis.URL` à la main (il n'y a pas de
// façon sûre de remplacer l'objet URL entier — cf. Step 0) : la restauration
// est explicite, `vi.unstubAllGlobals()` ne la fait pas.
let stub: ReturnType<typeof installImageDecodeStub> | undefined;
afterEach(() => {
  stub?.restore();
  stub = undefined;
  vi.unstubAllGlobals();
});

test("LUCIDE_ICONS contient exactement 140 entrées sur 7 catégories", () => {
  expect(LUCIDE_ICONS).toHaveLength(140);
  expect(new Set(LUCIDE_ICONS.map((i) => i.category))).toEqual(
    new Set([
      "generic",
      "buildings",
      "nature",
      "transport",
      "services",
      "safety-health",
      "leisure",
    ]),
  );
  for (const category of new Set(LUCIDE_ICONS.map((i) => i.category))) {
    expect(LUCIDE_ICONS.filter((i) => i.category === category)).toHaveLength(20);
  }
});

test("LUCIDE_ICONS n'a aucun nom en doublon", () => {
  const names = LUCIDE_ICONS.map((i) => i.name);
  expect(new Set(names).size).toBe(names.length);
});

// Le module généré est la source de vérité des pixels : un nom du catalogue
// absent du module généré signifie que gen-lucide-icons.mjs n'a pas été
// relancé après une modification du catalogue.
// Constat B4 (Bloquant) du 2026-08-28 : l'assertion précédente était
// `toMatch(/^<svg/)`. MESURÉE sur le tarball réel lucide-static@1.34.0 :
// **0 des 2035** fichiers commence par `<svg` après `.trim()` — tous
// commencent par `<!-- @license lucide-static v1.34.0 - ISC -->`, et ce
// commentaire est précisément la notice que la licence ISC oblige à conserver,
// donc le script ne le retire PAS. Le test échouait sur 140/140. Le plan
// énonçait d'ailleurs ce fait lui-même 40 lignes plus bas : c'était une
// contradiction interne, pas seulement une erreur.
test("chaque nom du catalogue a bien un SVG dans le module généré", () => {
  for (const { name } of LUCIDE_ICONS) {
    const svg = LUCIDE_ICON_SVGS[name];
    expect(svg, `SVG manquant pour "${name}"`).toBeDefined();
    // La notice ISC est en tête et doit y rester (obligation de licence).
    expect(svg, `notice ISC absente pour "${name}"`).toMatch(
      /^<!-- @license lucide-static v1\.34\.0 - ISC -->/,
    );
    expect(svg, `pas de <svg> dans "${name}"`).toContain("<svg");
  }
  expect(Object.keys(LUCIDE_ICON_SVGS)).toHaveLength(140);
});

test("rasterizeLucideIcon décode un nom connu et met le résultat en cache", async () => {
  stub = installImageDecodeStub();
  const { created, revoked } = stub;
  const first = await rasterizeLucideIcon("map-pin");
  const second = await rasterizeLucideIcon("map-pin");
  expect(first.width).toBeGreaterThan(0);
  expect(second).toBe(first);
  // Une seule URL d'objet créée (cache), et révoquée après décodage.
  expect(created).toHaveLength(1);
  expect(revoked).toEqual(created);
});

test("rasterizeLucideIcon rejette un nom inconnu sans créer d'URL d'objet", async () => {
  stub = installImageDecodeStub();
  const { created } = stub;
  await expect(rasterizeLucideIcon("pas-une-icone")).rejects.toThrow(/Icône Lucide inconnue/);
  expect(created).toEqual([]);
});

// Les SVG de lucide-static portent stroke="currentColor", qui vaut noir hors
// contexte CSS. Ce test VERROUILLE LA FORME ATTENDUE dans le module généré :
// si une version future de lucide-static change les guillemets ou réordonne
// l'attribut, le `split`/`join` de rasterizeLucideIcon deviendrait un no-op
// SILENCIEUX et les icônes retomberaient sur le noir. Mesuré sur le paquet
// réel : la sous-chaîne exacte `stroke="currentColor"` est présente dans les
// 140 fichiers (les attributs y sont un par ligne).
//
// Constat Mineur 3 du 2026-08-28 : c'est le TITRE de ce test qui était faux —
// il annonçait « la substitution est effective » alors qu'il asserte la
// présence de la forme NON substituée. Titre corrigé, assertion inchangée.
test('la forme stroke="currentColor" attendue par la substitution est présente dans le module généré', () => {
  expect(LUCIDE_ICON_SVGS["map-pin"]).toContain('stroke="currentColor"');
});

test("decodeIconImage propage l'échec de décodage et révoque quand même l'URL", async () => {
  stub = installImageDecodeStub({ failing: ["blob:stub/"] });
  const { created, revoked } = stub;
  await expect(decodeIconImage(new Blob(["x"], { type: "image/png" }))).rejects.toThrow(
    /image illisible/,
  );
  expect(revoked).toEqual(created);
});
