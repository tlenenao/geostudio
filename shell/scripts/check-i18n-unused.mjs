#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// REV-285(c) : clés du catalogue i18n jamais référencées dans le code. Même
// patron que check-i18n-coverage.mjs / check-raw-colors.mjs : parcours
// `readdirSync` sans glob (CI en Node 20, cf. check-raw-colors.mjs), mesure,
// échec si une clé morte apparaît — câblé dans `npm run lint`.
//
// Une clé est « citée » si elle apparaît entre "…", '…' ou `…` dans un
// .ts/.tsx non-test de src/ (hors le catalogue lui-même), ou si elle commence
// par un préfixe de gabarit dynamique (`extensions.field${…}`) ou par un
// préfixe d'allowlist (clé fournie par le cœur, jamais écrite côté shell).
// ponytail: recherche textuelle, pas d'AST — une clé citée seulement dans un
// commentaire passe pour utilisée ; passer à un parcours TS si ça mord.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = "src";
const CATALOG = "src/i18n/catalog.fr.ts";
const ALLOWLIST = "scripts/i18n-unused-allowlist.json";

export function catalogKeys(src) {
  return [...src.matchAll(/^\s+"([\w.]+)":/gm)].map((m) => m[1]);
}

// Le point est exigé : `q${x}` ou `joined_${f}` ne sont pas des clés i18n.
export function dynamicPrefixes(src) {
  return [...new Set([...src.matchAll(/`(\w+\.[\w.]*)\$\{/g)].map((m) => m[1]))];
}

export function findUnusedKeys(keys, source, allowPrefixes = []) {
  const prefixes = [...dynamicPrefixes(source), ...allowPrefixes];
  return keys.filter(
    (k) =>
      !source.includes(`"${k}"`) &&
      !source.includes(`'${k}'`) &&
      !source.includes(`\`${k}\``) &&
      !prefixes.some((p) => k.startsWith(p)),
  );
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (
      [".ts", ".tsx"].includes(extname(full)) &&
      !/\.test\.tsx?$/.test(entry) &&
      !entry.endsWith(".d.ts") &&
      full.replaceAll("\\", "/") !== CATALOG
    )
      out.push(full);
  }
  return out;
}

export function main() {
  const keys = catalogKeys(readFileSync(CATALOG, "utf8"));
  const source = walk(ROOT)
    .map((f) => readFileSync(f, "utf8"))
    .join("\n");
  const allow = JSON.parse(readFileSync(ALLOWLIST, "utf8")).map((e) => e.prefix);
  const unused = findUnusedKeys(keys, source, allow);
  if (unused.length > 0) {
    console.error(`Clés i18n jamais référencées dans src/ (${unused.length}) :`);
    unused.forEach((k) => console.error(`  ${k}`));
    console.error(
      "\nSupprimer la clé de src/i18n/catalog.fr.ts, ou, si elle est résolue dynamiquement " +
        `sans gabarit littéral, ajouter son préfixe à ${ALLOWLIST} avec une raison.`,
    );
    process.exit(1);
  }
  console.log(`OK : ${keys.length} clé(s) i18n, toutes référencées.`);
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) main();
