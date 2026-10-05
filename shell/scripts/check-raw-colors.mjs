#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Garde-fou anti-régression (SP-B12d, clôture du lot de tokenisation
// SP-34/lots 1-6) : signale une classe Tailwind de couleur LITTÉRALE
// (ex. `bg-red-600`, `text-white`) hors `ui/kit/` (design system, seul
// endroit qui a le droit de définir les tokens `--gs-*`). `map/` est scanné
// (REV-285 d) : ses défauts de symbologie portent un pragma motivé.
// Même patron architectural que check-i18n-coverage.mjs
// (SP-57a) : parcourt le code
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
// quand le patron `walk()` déjà utilisé par les autres scripts de scripts/
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
//
// REV-285(d) : les `.ts` sont scannés aussi (palettes de dataviz, thème
// d'app par défaut). Pour un BLOC de couleurs délibérées (palette), un pragma
// de région : `// gs-raw-color-ok-begin: <raison>` … `// gs-raw-color-ok-end`.
// Une région jamais fermée est elle-même une erreur (sinon elle couvrirait
// silencieusement tout le reste du fichier).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname, relative } from "node:path";

const ROOT = "src";

const RAW_COLOR_RE =
  /\b(text|bg|border)-(red|green|blue|yellow|slate|gray|zinc|neutral|stone|emerald|amber|orange|indigo|violet|purple|pink|rose|cyan|sky|teal|lime|white|black)(-[0-9]+)?(\/[0-9]+)?\b/;

// Couleurs hexadécimales littérales entre guillemets (dataviz, MapLibre) : à lire
// depuis un jeton --gs-* (lib/theme.ts readToken) ou à justifier par le pragma.
const HEX_COLOR_RE = /["'`]#[0-9a-fA-F]{3,8}["'`]/;

// (?!-) : les marqueurs de région -begin/-end ne sont pas des pragmas de ligne.
const PRAGMA_RE = /gs-raw-color-ok(?!-)/;
const REGION_BEGIN_RE = /\/\/\s*gs-raw-color-ok-begin\b/;
const REGION_END_RE = /\/\/\s*gs-raw-color-ok-end\b/;

/**
 * `true` si `relPath` (relatif à `src/`, séparateurs normalisés en `/`)
 * est `ui/kit` ou un de ses sous-dossiers.
 */
export function isExcludedDir(relPath) {
  const norm = relPath.replaceAll("\\", "/");
  return norm === "ui/kit" || norm.startsWith("ui/kit/");
}

/**
 * Parcours récursif de `dir` (sans dépendance de glob), retourne la
 * liste des fichiers .ts/.tsx non-test (hors .d.ts), en sautant `ui/kit/`.
 */
function walk(dir, root, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      const rel = relative(root, full);
      if (isExcludedDir(rel)) continue;
      walk(full, root, out);
    } else if (
      [".ts", ".tsx"].includes(extname(full)) &&
      !/\.test\.tsx?$/.test(entry) &&
      !entry.endsWith(".d.ts")
    ) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Retourne les lignes de `file` qui portent une couleur Tailwind
 * littérale sans pragma `gs-raw-color-ok` ou hors région `gs-raw-color-ok-begin`/`-end` (sur la ligne elle-même, ou
 * sur la ligne précédente SI ET SEULEMENT SI celle-ci, une fois
 * retirée des espaces en bordure, est un commentaire pur — commence par
 * `//` et ne porte que ça. Sans cette contrainte, un pragma en fin de
 * ligne sur une ligne qui contient AUSSI l'offense qu'il documente
 * "fuit" à tort sur la ligne suivante, non liée — cf. commentaire de
 * couverture de pragma en tête de fichier).
 */
export function findOffendersInSource(content, file) {
  const lines = content.split("\n");
  const offenders = [];
  let regionStart = -1;
  lines.forEach((line, index) => {
    if (REGION_BEGIN_RE.test(line)) {
      regionStart = index;
      return;
    }
    if (REGION_END_RE.test(line)) {
      regionStart = -1;
      return;
    }
    if (regionStart >= 0) return;
    if (!RAW_COLOR_RE.test(line) && !HEX_COLOR_RE.test(line)) return;
    const coveredBySameLine = PRAGMA_RE.test(line);
    const prevLineTrimmed = index > 0 ? lines[index - 1].trim() : "";
    const coveredByPrecedingLine =
      prevLineTrimmed.startsWith("//") && PRAGMA_RE.test(prevLineTrimmed);
    if (coveredBySameLine || coveredByPrecedingLine) return;
    offenders.push(`${file}:${index + 1}: ${line.trim()}`);
  });
  if (regionStart >= 0) {
    offenders.push(
      `${file}:${regionStart + 1}: région gs-raw-color-ok-begin jamais fermée par gs-raw-color-ok-end`,
    );
  }
  return offenders;
}

function findOffenders(file) {
  return findOffendersInSource(readFileSync(file, "utf8"), file);
}

export function main() {
  const files = walk(ROOT, ROOT).sort();
  const offenders = files.flatMap(findOffenders);

  if (offenders.length > 0) {
    console.error(
      "Couleurs Tailwind brutes détectées hors ui/kit/ (.ts/.tsx), sans pragma gs-raw-color-ok :",
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
    `OK : aucune couleur Tailwind brute hors ui/kit/, tests et pragma gs-raw-color-ok (${files.length} fichier(s) scanné(s)).`,
  );
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main();
}
