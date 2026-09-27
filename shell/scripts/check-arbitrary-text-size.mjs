#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Garde-fou anti-régression (SP-C3/D46) : signale une classe Tailwind de
// taille de texte ARBITRAIRE (`text-[10px]`, `text-[9px]`, etc.) hors test.
// L'échelle typographique Tailwind v4 par défaut n'a aucun palier entre
// `text-xs` (12px) et rien — ces occurrences ponctuelles contournaient
// toujours le contrat de tokens (cf. tokens.css, `--text-2xs` ajouté par la
// même tâche pour les badges dont la taille est contrainte). Même patron
// architectural que check-raw-colors.mjs (SP-B12d) : parcourt le code
// source, échoue si une occurrence n'est pas couverte par un pragma
// explicite — câblé dans `npm run lint`.
//
// Contrairement à check-raw-colors.mjs, AUCUN répertoire n'est exclu :
// `map/` n'a pas ici la légitimité qu'il a pour les couleurs de symbologie
// choisies par l'utilisateur final (check-raw-colors.mjs) — une taille de
// texte arbitraire dans `map/` (ex. MapSymbologyEditor.tsx) est le même
// défaut qu'ailleurs, pas un choix produit.
//
// Choix d'implémentation identique à check-raw-colors.mjs : parcours manuel
// `readdirSync`/`statSync` (pas de glob — `.github/workflows/ci.yml` lance
// Node 20 sur tous les jobs shell, `node:fs` `globSync` nécessite Node >=
// 22).
//
// Allowlist — pragma EN LIGNE, pas un allowlist par fichier (même raison
// que check-raw-colors.mjs : un allowlist par fichier laisserait un nouvel
// offenseur non lié se glisser, non détecté, dans un fichier déjà
// exempté) : `// gs-arbitrary-text-size-ok: <raison>` sur la même ligne
// physique que l'occurrence, ou sur la ligne immédiatement précédente SI ET
// SEULEMENT SI celle-ci, une fois retirée des espaces en bordure, est un
// commentaire pur.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = "src";

const ARBITRARY_TEXT_SIZE_RE = /\btext-\[[0-9]+px\]/;

const PRAGMA_RE = /gs-arbitrary-text-size-ok/;

/**
 * Parcours récursif de `dir` (sans dépendance de glob), retourne la liste
 * des fichiers `.tsx` non-test.
 */
function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      walk(full, out);
    } else if (extname(full) === ".tsx" && !entry.endsWith(".test.tsx")) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Retourne les lignes de `file` qui portent une taille de texte Tailwind
 * arbitraire sans pragma `gs-arbitrary-text-size-ok` (sur la ligne
 * elle-même, ou sur la ligne précédente si et seulement si celle-ci est un
 * commentaire pur — même garde anti-fuite que check-raw-colors.mjs).
 */
function findOffenders(file) {
  const content = readFileSync(file, "utf8");
  const lines = content.split("\n");
  const offenders = [];
  lines.forEach((line, index) => {
    if (!ARBITRARY_TEXT_SIZE_RE.test(line)) return;
    const coveredBySameLine = PRAGMA_RE.test(line);
    const prevLine = index > 0 ? lines[index - 1] : "";
    const prevLineTrimmed = prevLine.trim();
    const coveredByPrecedingLine =
      prevLineTrimmed.startsWith("//") && PRAGMA_RE.test(prevLineTrimmed);
    if (coveredBySameLine || coveredByPrecedingLine) return;
    offenders.push(`${file}:${index + 1}: ${line.trim()}`);
  });
  return offenders;
}

export function main() {
  const files = walk(ROOT).sort();
  const offenders = files.flatMap(findOffenders);

  if (offenders.length > 0) {
    console.error(
      "Tailles de texte Tailwind arbitraires détectées (text-[Npx]), sans pragma gs-arbitrary-text-size-ok :",
    );
    offenders.forEach((o) => console.error(`  ${o}`));
    console.error(
      "\nUtiliser un token sémantique (text-xs, ou text-2xs pour un badge dont la taille " +
        "est contrainte) au lieu d'une taille littérale, ou documenter l'exception avec " +
        "`// gs-arbitrary-text-size-ok: <raison>` sur la même ligne ou la ligne précédente " +
        "si l'exception est délibérée et revue.",
    );
    process.exit(1);
  }
  console.log(
    `OK : aucune taille de texte Tailwind arbitraire hors tests et pragma gs-arbitrary-text-size-ok (${files.length} fichier(s) scanné(s)).`,
  );
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main();
}
