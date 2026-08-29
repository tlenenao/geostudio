// SPDX-License-Identifier: Apache-2.0
// Matérialise le sous-ensemble curaté de lucide-static (ISC) dans un module
// TS committé. Aucune magie de bundler : ni import dynamique entièrement
// templaté, ni import.meta.glob sur /node_modules (aucune des deux formes
// n'a pu être vérifiée contre la version de Vite du dépôt, et la seconde
// émettrait ~2035 assets minuscules dans le build). Le script lit les 140
// noms depuis iconLibrary.ts et écrit lucideIconSvgs.generated.ts.
//
// Usage : cd shell && npm run gen:lucide-icons
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ICONS_DIR = join("node_modules", "lucide-static", "icons");
const SOURCE = join("src", "builder", "widgets", "iconLibrary.ts");
const TARGET = join("src", "builder", "widgets", "lucideIconSvgs.generated.ts");

// Extrait les littéraux de chaîne des VALEURS (les tableaux) d'ICON_NAMES,
// jamais de ses CLÉS.
//
// Constat B3 (Bloquant) du 2026-08-28 : la version précédente faisait
// `[...block.matchAll(/"([a-z0-9-]+)"/g)]` sur tout le bloc. MESURÉ sur le
// texte réel du catalogue : 141 correspondances, parce que la clé de catégorie
// `"safety-health"` est la seule des sept écrite entre guillemets (elle
// contient un tiret, donc TypeScript l'exige) et qu'elle matche la même
// expression. Le script levait donc « attendu 140 noms … trouvé 141 » à chaque
// exécution, et si l'assertion avait été desserrée l'itération suivante aurait
// fait `readFileSync("node_modules/lucide-static/icons/safety-health.svg")` →
// ENOENT. Pire, le Step 4 envoyait l'implémenteur « corriger le catalogue, pas
// l'assertion » — donc casser un catalogue correct.
//
// Correctif : on ne lit que l'intérieur des littéraux de tableau. MESURÉ sur
// le catalogue réel : 8 tableaux trouvés (le premier, vide, vient du
// `string[]` de l'annotation de type), 7 × 20 = 140 noms, 140 uniques.
const src = readFileSync(SOURCE, "utf8");
const block = src.slice(
  src.indexOf("const ICON_NAMES: Record<IconCategory, string[]> = {"),
  src.indexOf("export const LUCIDE_ICONS"),
);
if (block.length === 0) {
  throw new Error(`bloc ICON_NAMES introuvable dans ${SOURCE}`);
}
const arrays = [...block.matchAll(/\[([^\]]*)\]/g)].map((m) => m[1]);
const names = arrays.flatMap((body) => [...body.matchAll(/"([a-z0-9-]+)"/g)].map((m) => m[1]));
const unique = [...new Set(names)];
if (unique.length !== names.length) {
  throw new Error(`noms dupliqués dans ${SOURCE}`);
}
if (names.length !== 140) {
  throw new Error(`attendu 140 noms dans ${SOURCE}, trouvé ${names.length}`);
}

const entries = names.map((name) => {
  const svg = readFileSync(join(ICONS_DIR, `${name}.svg`), "utf8").trim();
  return `  ${JSON.stringify(name)}: ${JSON.stringify(svg)},`;
});

writeFileSync(
  TARGET,
  `// SPDX-License-Identifier: Apache-2.0
// FICHIER GÉNÉRÉ — ne pas éditer à la main.
// Régénérer : cd shell && npm run gen:lucide-icons
//
// Contenu : ${names.length} pictogrammes de Lucide (https://lucide.dev),
// distribués sous licence ISC via le paquet npm lucide-static@1.34.0.
// Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as
// part of Feather (MIT). All other copyright (c) for Lucide are held by
// Lucide Contributors 2022. Licence ISC conservée telle quelle.
export const LUCIDE_ICON_SVGS: Record<string, string> = {
${entries.join("\n")}
};
`,
  "utf8",
);
console.log(`écrit ${TARGET} (${names.length} icônes)`);
