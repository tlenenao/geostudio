#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Garde-fou anti-régression (Tâche 33, referme la classe de défaut de la
// Tâche 3 — migration de `window.confirm` vers `ui/kit/ConfirmDialog`) :
// signale toute occurrence littérale de `window.confirm(` hors
// `ui/kit/ConfirmDialog.tsx` lui-même et hors fichiers de test. Sans ce
// garde, un futur ajout peut réintroduire un `window.confirm` sans
// qu'aucun test ne le remarque. Même patron architectural que
// check-raw-colors.mjs / check-aria-panel-coverage.mjs /
// check-i18n-coverage.mjs (SP-34/SP-43/SP-57a) : parcourt le code source,
// échoue si l'invariant est violé, câblé dans `npm run lint`.
//
// Choix d'implémentation — parcours manuel `readdirSync`/`statSync` (pas
// de glob) : `node:fs` `globSync` nécessite Node >= 22 ;
// `.github/workflows/ci.yml` lance explicitement `node-version: 20` sur
// tous les jobs shell — un `globSync` casserait silencieusement en CI
// (piège déjà rencontré et corrigé sur check-raw-colors.mjs, Tâche 32).
//
// Exclusion — UN SEUL fichier fixe (`ui/kit/ConfirmDialog.tsx`), pas un
// répertoire entier : contrairement au sweep de couleurs (Tâche 32), il
// n'y a pas plusieurs sites légitimes à exempter, donc pas de mécanisme
// de pragma ici. Note : au moment d'écrire ce script, ConfirmDialog.tsx
// ne contient plus lui-même `window.confirm(` (entièrement remplacé par
// `Dialog`/`Button`) — l'exclusion est donc actuellement inerte, mais
// gardée par prudence (si un jour une implémentation interne y revenait).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname, relative } from "node:path";

const ROOT = "src";
const EXCLUDED_FILE = "ui/kit/ConfirmDialog.tsx";

/**
 * Parcours récursif de `dir` (sans dépendance de glob), retourne la
 * liste des fichiers `.tsx` non-test, en sautant `EXCLUDED_FILE`.
 */
function walk(dir, root, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      walk(full, root, out);
    } else if (extname(full) === ".tsx" && !entry.endsWith(".test.tsx")) {
      const rel = relative(root, full).replaceAll("\\", "/");
      if (rel === EXCLUDED_FILE) continue;
      out.push(full);
    }
  }
  return out;
}

/**
 * Retourne les lignes de `file` qui contiennent un appel littéral à
 * `window.confirm(`.
 */
function findOffenders(file) {
  const content = readFileSync(file, "utf8");
  const lines = content.split("\n");
  const offenders = [];
  lines.forEach((line, index) => {
    if (line.includes("window.confirm(")) {
      offenders.push(`${file}:${index + 1}: ${line.trim()}`);
    }
  });
  return offenders;
}

export function main() {
  const files = walk(ROOT, ROOT).sort();
  const offenders = files.flatMap(findOffenders);

  if (offenders.length > 0) {
    console.error(
      `window.confirm() détecté hors ${EXCLUDED_FILE} — utiliser ui/kit/ConfirmDialog :`,
    );
    offenders.forEach((o) => console.error(`  ${o}`));
    process.exit(1);
  }
  console.log(
    `OK : aucun window.confirm() résiduel hors ${EXCLUDED_FILE} et tests (${files.length} fichier(s) scanné(s)).`,
  );
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main();
}
