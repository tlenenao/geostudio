#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Détecteur de couverture i18n (GAP-14, SP-57a) : signale les chaînes
// littérales françaises codées en dur dans pages/shell/builder/map, hors
// t(). Heuristique documentée (spec SP-57a §2.2) : faux positifs (identifiant
// contenant un mot de la liste, message console non-UI) et faux négatifs
// (texte français sans accent ni mot de la liste) possibles — chaque
// violation reportée doit être inspectée avant d'être corrigée ou exclue via
// l'allowlist, jamais corrigée aveuglément.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, extname, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Mots français fréquents sans accent, liste curatée courte. « fermer » a été
// ajouté à la liste du texte de la spec (SP-57a §2.2) : le fixture de test du
// détecteur (plan Task 1 Step 1) exige qu'aria-label="Fermer" soit détecté
// par la liste de mots (aucun accent) — absent de la liste initiale du
// document, ajout documenté ici plutôt que silencieux (piège CLAUDE.md n°3).
const FRENCH_WORDS = [
  "le",
  "la",
  "les",
  "de",
  "des",
  "du",
  "un",
  "une",
  "et",
  "ou",
  "pour",
  "dans",
  "avec",
  "sans",
  "sur",
  "ce",
  "cette",
  "ces",
  "nouveau",
  "nouvelle",
  "supprimer",
  "ajouter",
  "modifier",
  "enregistrer",
  "annuler",
  "fermer",
];
const FRENCH_WORDS_RE = new RegExp(`\\b(${FRENCH_WORDS.join("|")})\\b`, "i");
const ACCENT_RE = /[àâäéèêëïîôöùûüçÀÂÄÉÈÊËÏÎÔÖÙÛÜÇ]/;

function looksFrench(text) {
  return ACCENT_RE.test(text) || FRENCH_WORDS_RE.test(text);
}

function lineAt(content, index) {
  let line = 1;
  for (let i = 0; i < index && i < content.length; i++) {
    if (content[i] === "\n") line++;
  }
  return line;
}

function blank(text) {
  return text.replace(/[^\n]/g, " ");
}

function stripBlockComments(content) {
  return content.replace(/\/\*[\s\S]*?\*\//g, blank);
}

function stripLineComments(content) {
  return content
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, (m) => blank(m)))
    .join("\n");
}

function stripImportLines(content) {
  return content
    .split("\n")
    .map((line) => (/^\s*import\b/.test(line) ? blank(line) : line))
    .join("\n");
}

// Neutralise le premier argument littéral d'un appel t("...") : c'est la clé
// du catalogue, pas une fuite de texte (spec §2.2) — ne doit jamais être
// flaguée.
function stripTLiteralArgs(content) {
  return content.replace(
    /\bt\(\s*(["'])((?:\\.|(?!\1)[^\\])*)\1/g,
    (m, q, inner) => `t(${q}${blank(inner)}${q}`,
  );
}

function preprocess(content) {
  let out = stripBlockComments(content);
  out = stripLineComments(out);
  out = stripImportLines(out);
  out = stripTLiteralArgs(out);
  return out;
}

const STRING_RE = /"([^"\\]*(?:\\.[^"\\]*)*)"|'([^'\\]*(?:\\.[^'\\]*)*)'/g;
const JSX_TEXT_RE = />([^<>{}]+)</g;

/**
 * Détecte les chaînes littérales françaises codées en dur dans un contenu de
 * fichier .tsx : chaînes entre guillemets (attributs JSX, propriétés d'objet,
 * variables) et texte JSX statique entre balises. Ignore les commentaires,
 * les lignes `import`, et le premier argument littéral d'un appel `t(`.
 */
export function detectViolations(fileContent) {
  const violations = [];
  const seen = new Set();
  const processed = preprocess(fileContent);

  for (const match of processed.matchAll(STRING_RE)) {
    const value = match[1] ?? match[2] ?? "";
    if (!looksFrench(value)) continue;
    const line = lineAt(processed, match.index);
    const key = `${line}:${match[0]}`;
    if (seen.has(key)) continue;
    seen.add(key);
    violations.push({ line, snippet: match[0].trim().slice(0, 120) });
  }

  for (const match of processed.matchAll(JSX_TEXT_RE)) {
    const value = match[1];
    if (!value.trim() || !looksFrench(value)) continue;
    const line = lineAt(processed, match.index);
    const key = `${line}:${value.trim()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    violations.push({ line, snippet: value.trim().slice(0, 120) });
  }

  violations.sort((a, b) => a.line - b.line);
  return violations;
}

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

function loadAllowlist(path) {
  if (!path || !existsSync(path)) return new Set();
  try {
    const raw = JSON.parse(readFileSync(path, "utf-8"));
    return new Set(raw);
  } catch {
    return new Set();
  }
}

/**
 * CLI : parcourt `targetDirs`, rapporte chaque violation ; sort en erreur
 * (exit 1) si une violation existe hors de `allowlistPath`.
 */
export function main(targetDirs, allowlistPath) {
  const allowlist = loadAllowlist(allowlistPath);
  let files = [];
  for (const dir of targetDirs) files = files.concat(walk(dir));
  files.sort();

  let failing = false;
  let violationCount = 0;
  for (const file of files) {
    const content = readFileSync(file, "utf-8");
    const violations = detectViolations(content);
    if (violations.length === 0) continue;
    const excluded = allowlist.has(file);
    for (const v of violations) {
      const prefix = excluded ? "(allowlist) " : "";
      console.log(`${prefix}${file}:${v.line}: ${v.snippet}`);
    }
    violationCount += violations.length;
    if (!excluded) failing = true;
  }

  if (failing) {
    console.error(
      `\nÉCHEC : chaînes françaises codées en dur hors allowlist (${violationCount} occurrence(s) au total, voir ci-dessus).`,
    );
    process.exit(1);
  }
  console.log(
    `OK : aucune chaîne française codée en dur hors allowlist (${violationCount} en allowlist).`,
  );
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const defaultAllowlist = join(scriptDir, "i18n-coverage-allowlist.json");
  const args = process.argv.slice(2);
  const allowlistIdx = args.indexOf("--allowlist");
  let allowlistPath = defaultAllowlist;
  let dirs = args;
  if (allowlistIdx !== -1) {
    allowlistPath = args[allowlistIdx + 1];
    dirs = [...args.slice(0, allowlistIdx), ...args.slice(allowlistIdx + 2)];
  }
  // Chemins relatifs à la racine shell/, indépendamment du cwd d'où le
  // script est appelé — cohérent avec les entrées de l'allowlist
  // (`src/pages/Foo.tsx`).
  dirs = dirs.map((d) => relative(process.cwd(), join(process.cwd(), d)));
  main(dirs, allowlistPath);
}
