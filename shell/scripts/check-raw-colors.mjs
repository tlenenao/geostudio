#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Garde-fou anti-régression (SP-B12d, clôture du lot de tokenisation
// SP-34/lots 1-6) : signale une classe Tailwind de couleur LITTÉRALE
// (ex. `bg-red-600`, `text-white`) hors `ui/kit/` (design system, seul
// endroit qui a le droit de définir les tokens `--gs-*`) et `map/`
// (symbologie choisie par l'utilisateur final, pas l'ambiance studio).
// Même patron architectural que check-i18n-coverage.mjs /
// check-aria-panel-coverage.mjs (SP-57a/SP-43) : parcourt le code
// source, calcule une mesure, échoue si elle régresse — câblé dans
// `npm run lint`.
//
// Choix d'implémentation — parcours manuel `readdirSync`/`statSync`
// (pas de glob) : `node:fs` `globSync` nécessite Node >= 22 ; le poste
// de dev qui a écrit ce script tourne Node 22, mais
// `.github/workflows/ci.yml` lance explicitement `node-version: 20` sur
// tous les jobs shell — un `globSync` marcherait ici et casserait
// silencieusement en CI. `fast-glob` n'est PAS une dépendance de ce
// dépôt (vérifié dans package.json avant d'écrire ce script) : ajouter
// une dépendance neuve pour un script utilitaire n'est pas justifié
// quand le patron `walk()` déjà utilisé par check-aria-panel-coverage.mjs
// fait le travail sans dépendance et sans contrainte de version Node.
//
// Allowlist — un pragma EN LIGNE, pas un allowlist par fichier (un
// allowlist par fichier laisserait un nouvel offenseur non lié se
// glisser, non détecté, dans un fichier déjà exempté) :
// `// gs-raw-color-ok: <raison>` sur la même ligne physique que
// l'occurrence, ou sur la ligne immédiatement précédente. 6 fichiers du
// dépôt portent une exception délibérée déjà revue en Tâche 31 (chrome
// d'export/impression figé en blanc quel que soit le thème ; texte/bouton
// à contraste fixe sur `--gs-color-primary`, la couleur configurable par
// l'auteur d'app, pas l'ambiance du studio) — le pragma y est déjà posé.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname, relative } from "node:path";

const ROOT = "src";

const RAW_COLOR_RE =
  /\b(text|bg|border)-(red|green|blue|yellow|slate|gray|zinc|neutral|stone|emerald|amber|orange|indigo|violet|purple|pink|rose|cyan|sky|teal|lime|white|black)(-[0-9]+)?(\/[0-9]+)?\b/;

const PRAGMA_RE = /gs-raw-color-ok/;

/**
 * `true` si `relPath` (relatif à `src/`, séparateurs normalisés en `/`)
 * est `ui/kit` ou `map`, ou un de leurs sous-dossiers.
 */
function isExcludedDir(relPath) {
  const norm = relPath.replaceAll("\\", "/");
  return (
    norm === "ui/kit" || norm.startsWith("ui/kit/") || norm === "map" || norm.startsWith("map/")
  );
}

/**
 * Parcours récursif de `dir` (sans dépendance de glob), retourne la
 * liste des fichiers `.tsx` non-test, en sautant `ui/kit/` et `map/`.
 */
function walk(dir, root, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      const rel = relative(root, full);
      if (isExcludedDir(rel)) continue;
      walk(full, root, out);
    } else if (extname(full) === ".tsx" && !entry.endsWith(".test.tsx")) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Retourne les lignes de `file` qui portent une couleur Tailwind
 * littérale sans pragma `gs-raw-color-ok` (sur la ligne elle-même ou
 * la ligne précédente).
 */
function findOffenders(file) {
  const content = readFileSync(file, "utf8");
  const lines = content.split("\n");
  const offenders = [];
  lines.forEach((line, index) => {
    if (!RAW_COLOR_RE.test(line)) return;
    const coveredBySameLine = PRAGMA_RE.test(line);
    const prevLine = index > 0 ? lines[index - 1] : "";
    const coveredByPrecedingLine = PRAGMA_RE.test(prevLine);
    if (coveredBySameLine || coveredByPrecedingLine) return;
    offenders.push(`${file}:${index + 1}: ${line.trim()}`);
  });
  return offenders;
}

export function main() {
  const files = walk(ROOT, ROOT).sort();
  const offenders = files.flatMap(findOffenders);

  if (offenders.length > 0) {
    console.error(
      "Couleurs Tailwind brutes détectées hors ui/kit/ et map/, sans pragma gs-raw-color-ok :",
    );
    offenders.forEach((o) => console.error(`  ${o}`));
    console.error(
      "\nUtiliser un token sémantique (--gs-color-*) au lieu d'une classe littérale, ou " +
        "documenter l'exception avec `// gs-raw-color-ok: <raison>` sur la même ligne " +
        "ou la ligne précédente si l'exception est délibérée et revue.",
    );
    process.exit(1);
  }
  console.log(
    `OK : aucune couleur Tailwind brute hors ui/kit/, map/, tests et pragma gs-raw-color-ok (${files.length} fichier(s) scanné(s)).`,
  );
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main();
}
