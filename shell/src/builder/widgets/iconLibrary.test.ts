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

// Trou 1 (revue du 2026-08-28) : le seul test touchant à la substitution de
// couleur lisait `LUCIDE_ICON_SVGS["map-pin"]` DIRECTEMENT (cf. le test
// ci-dessus, qui asserte volontairement la forme NON substituée du module
// généré) — il ne passe jamais par `rasterizeLucideIcon`. Si le
// `split`/`join` de `rasterizeLucideIcon` devenait un no-op silencieux, rien
// ne le détecterait : les icônes retomberaient toutes sur `currentColor`
// (donc noir hors CSS), en silence. Ce test lit le texte RÉEL du Blob
// effectivement passé à `decodeIconImage` (capturé par le double via son
// `.text()`), donc ce qui a vraiment traversé la fonction sous test.
// Nom d'icône dédié ("flag"), distinct de "map-pin" déjà utilisé plus haut :
// `imageCache` est un `Map` de portée module, partagé par tous les tests de
// ce fichier (aucun reset entre tests) — réutiliser "map-pin" ferait
// retomber sur l'entrée déjà résolue et mise en cache par le test "décode un
// nom connu…", sans jamais rappeler `decodeIconImage`.
test('rasterizeLucideIcon substitue réellement stroke="currentColor" par une couleur concrète', async () => {
  stub = installImageDecodeStub();
  await rasterizeLucideIcon("flag");
  expect(stub.contents).toHaveLength(1);
  const painted = await stub.contents[0];
  expect(painted).not.toContain('stroke="currentColor"');
  // Couleur concrète documentée par `LUCIDE_STROKE` dans iconLibrary.ts —
  // non exportée (constante privée du module), donc dupliquée ici sciemment.
  expect(painted).toContain('stroke="#1e293b"');
});

// Trou 2 (revue du 2026-08-28) : la branche `catch` de `rasterizeLucideIcon`
// (lignes 221-227) évince l'entrée de cache après un échec de décodage puis
// relance l'erreur — c'est la seule garantie que le mécanisme est réparable.
// Rien ne prouvait qu'un second appel après un échec relance vraiment un
// nouveau décodage plutôt que de rester bloqué sur la promesse rejetée mise
// en cache. `failing: ["star"]` fait échouer le décodage sur la base du
// contenu réel du SVG (attribut `class="lucide lucide-star"`), pas de l'URL
// opaque — donc un nom connu du catalogue, précisément le cas visé. Nom
// dédié ("star"), pour la même raison de cache partagé que le test
// précédent.
test("rasterizeLucideIcon évince le cache après un échec et relance un nouveau décodage", async () => {
  stub = installImageDecodeStub({ failing: ["star"] });
  const { created } = stub;
  await expect(rasterizeLucideIcon("star")).rejects.toThrow(/image illisible/);
  expect(created).toHaveLength(1);
  // Un nouvel appel après l'échec doit relancer un nouveau décodage — donc
  // créer une seconde URL d'objet — et non rester bloqué sur la promesse
  // rejetée précédemment mise en cache.
  stub.restore();
  stub = installImageDecodeStub();
  const image = await rasterizeLucideIcon("star");
  expect(image.width).toBeGreaterThan(0);
  expect(stub.created).toHaveLength(1);
});
