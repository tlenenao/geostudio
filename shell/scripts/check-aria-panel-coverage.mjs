#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Détecteur de couverture aria-expanded/aria-controls (REV-059/REV-088) :
// signale un <button>/<Button> qui a toutes les apparences d'un déclencheur
// de panneau en ligne (il bascule un état booléen de visibilité) sans
// porter `aria-expanded`/`aria-controls`, ni relayer `usePanelTrigger`
// (`shell/src/ui/kit/usePanelTrigger.ts`, patron de référence — spread
// `{...xxx.triggerProps}`). Même patron architectural que
// check-i18n-coverage.mjs (SP-57a) : un script qui scanne le code source,
// calcule une mesure, échoue si elle régresse — câblé dans `npm run lint`.
//
// Heuristique documentée (pas un vrai parseur AST) :
// - Un élément <button ...> ou <Button ...> est un « candidat trigger » si
//   son attribut onClick (le seul gestionnaire regardé — onPointerDown/
//   onMouseDown ne le sont pas) appelle, dans son corps, un setter d'état
//   React qui OUVRE un booléen : `setXxx(true)` ou `setXxx(!xxx)`
//   (négation, direction ambiguë donc gardée), ou `.toggle(`. `setXxx(false)`
//   seul est délibérément IGNORÉ : c'est typiquement le bouton "Annuler"/
//   "Fermer" à l'intérieur du panneau qui referme, pas le déclencheur que
//   vise la convention — mesuré en pratique sur ce dépôt (cf. commentaire
//   sur TOGGLE_CALL_RE plus bas), retenir aussi "false" aurait produit un
//   faux positif sur la moitié des candidats du premier passage.
// - Il est considéré câblé (ignoré) si son attribut list porte à la fois
//   `aria-expanded=` et `aria-controls=`, OU un spread
//   `{...xxx.triggerProps}` (la forme que rend usePanelTrigger()).
// - L'extraction de « l'attribut list » d'un élément JSX se fait par un
//   scanner à profondeur d'accolades (pas une regex plate) : depuis
//   `<button`/`<Button`, on avance jusqu'au `>` de fermeture qui n'est
//   contenu dans aucune accolade `{...}` ni chaîne littérale — nécessaire
//   car `onClick={() => { ... }}` contient lui-même des `{`/`}` et parfois
//   des `>` (comparaisons, JSX imbriqué) qui ne doivent pas être confondus
//   avec la fermeture de balise.
//
// Faux positifs documentés (à trier manuellement avant correction ou
// allowlist, jamais corrigés aveuglément — même doctrine que l'allowlist
// i18n) — les deux classes suivantes couvrent la totalité des faux
// positifs réels trouvés en balayant tout `src/` à l'écriture de ce
// script (cf. aria-panel-coverage-allowlist.json) :
// - Le panneau réellement ouvert est une boîte de dialogue MODALE
//   (`ui/dialog.tsx` role="dialog", `ui/kit/Drawer.tsx`/`ui/kit/Dialog.tsx`
//   Radix, `ui/kit/ConfirmDialog.tsx`, un `ui/kit/Toast.tsx`…) — la
//   convention CLAUDE.md vise le panneau *en ligne* (une région qui
//   apparaît dans le flux de la page), pas une boîte de dialogue modale ni
//   une notification transitoire. Le script ne corrèle jamais l'état
//   basculé au composant qui le consomme réellement plus bas dans le JSX
//   (coût d'un vrai parseur AST, hors périmètre) : tout bouton qui ouvre
//   ainsi un composant modal est structurellement indiscernable d'un vrai
//   déclencheur de panneau en ligne pour ce détecteur.
// - Un bouton qui bascule un booléen sans rapport avec un panneau visuel
//   du tout (aucun cas réel trouvé sur ce dépôt à ce jour, mais
//   plausible : ex. un `setChecked(true)` de contrôle maison).
//
// Faux négatifs documentés :
// - Un toggle par updater fonctionnel (`setOpen((o) => !o)`) ou par
//   dispatch de réducteur (`dispatch({ type: "TOGGLE_PANEL" })`) n'est pas
//   reconnu par les motifs `set[A-Z]\w*\(...\)`/`.toggle(` ci-dessus.
// - Un déclencheur qui n'est ni un `<button>` ni un `<Button` (ex. un
//   `<a>`/`<div role="button">`) n'est jamais scanné.
// - `aria-expanded`/`aria-controls` posés mais avec des valeurs erronées
//   (ex. codées en dur, jamais réactives) ne sont pas vérifiés — seule leur
//   présence littérale dans l'attribut list compte.
// - Un vrai déclencheur de panneau en ligne qui ferme (jamais n'ouvre) via
//   un `setXxx(false)` isolé (aucun `setXxx(true)` ni négation nulle part
//   dans le même onClick) échappe totalement au détecteur — cf. exclusion
//   volontaire de "false" ci-dessus, contrepartie assumée.
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, extname, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

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

function preprocess(content) {
  return stripLineComments(stripBlockComments(content));
}

function lineAt(content, index) {
  let line = 1;
  for (let i = 0; i < index && i < content.length; i++) {
    if (content[i] === "\n") line++;
  }
  return line;
}

const TRIGGER_OPEN_RE = /<(button|Button)\b/g;

/**
 * Depuis l'index d'un `<button`/`<Button`, retourne la sous-chaîne allant
 * jusqu'au `>` qui ferme réellement la balise (profondeur d'accolades 0,
 * hors chaîne littérale). `null` si jamais trouvé dans les 8000 caractères
 * suivants (borne de sécurité contre un fichier malformé).
 */
function extractOpeningTag(content, startIndex) {
  const CAP = 8000;
  let braceDepth = 0;
  let inString = null; // null | '"' | "'" | '`'
  for (let i = startIndex; i < Math.min(content.length, startIndex + CAP); i++) {
    const ch = content[i];
    const prev = content[i - 1];
    if (inString) {
      if (ch === inString && prev !== "\\") inString = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      inString = ch;
      continue;
    }
    if (ch === "{") {
      braceDepth++;
      continue;
    }
    if (ch === "}") {
      braceDepth = Math.max(0, braceDepth - 1);
      continue;
    }
    if (ch === ">" && braceDepth === 0) {
      return content.slice(startIndex, i + 1);
    }
  }
  return null;
}

const ONCLICK_RE = /\bonClick\s*=\s*\{([\s\S]*)/;
// `true` seul (pas `false`) : un bouton qui referme un panneau
// (`setOpen(false)`, souvent le bouton "Annuler"/"Fermer" *à l'intérieur*
// du panneau lui-même) n'est pas le déclencheur que cible la convention
// CLAUDE.md — c'est le bouton qui l'ouvre qui doit porter
// aria-expanded/aria-controls, pas celui qui le ferme. Mesuré en pratique
// sur ce dépôt : sans cette restriction, la moitié des 15 candidats
// trouvés lors du premier passage étaient des boutons "Annuler" internes
// (AppExportPanel.tsx, print/ExportPanel.tsx, MapSymbologyEditor.tsx,
// AppRuntimePage.tsx) — un vrai faux positif de masse, corrigé ici plutôt
// que documenté en allowlist un par un.
const TOGGLE_CALL_RE = /\bset[A-Z]\w*\(\s*true\s*\)/;
// Négation (`setOpen(!open)`) : ambigu (ouvre ou ferme selon l'état
// courant), donc pas filtrable comme "false" ci-dessus — un seul bouton
// qui fait à la fois office d'ouverture et de fermeture doit à lui seul
// refléter l'état via aria-expanded, gardé comme candidat.
const TOGGLE_NEGATION_RE = /\bset[A-Z]\w*\(\s*!\s*[\w.]/;
const TOGGLE_METHOD_RE = /\.toggle\(/;
const ARIA_EXPANDED_RE = /\baria-expanded\s*=/;
const ARIA_CONTROLS_RE = /\baria-controls\s*=/;
const TRIGGER_PROPS_SPREAD_RE = /\{\s*\.\.\.[\w.$]*triggerProps\s*\}/;

function looksLikeVisibilityToggle(onClickBody) {
  return (
    TOGGLE_CALL_RE.test(onClickBody) ||
    TOGGLE_NEGATION_RE.test(onClickBody) ||
    TOGGLE_METHOD_RE.test(onClickBody)
  );
}

/**
 * Détecte, dans le contenu d'un fichier .tsx, les <button>/<Button> qui
 * ressemblent à un déclencheur de panneau (bascule un booléen de
 * visibilité via onClick) sans câblage aria-expanded/aria-controls ni
 * usePanelTrigger().
 */
export function detectViolations(fileContent) {
  const violations = [];
  const processed = preprocess(fileContent);

  for (const match of processed.matchAll(TRIGGER_OPEN_RE)) {
    const tag = extractOpeningTag(processed, match.index);
    if (tag === null) continue;

    const onClickMatch = tag.match(ONCLICK_RE);
    if (!onClickMatch) continue;
    if (!looksLikeVisibilityToggle(onClickMatch[1])) continue;

    const wired =
      (ARIA_EXPANDED_RE.test(tag) && ARIA_CONTROLS_RE.test(tag)) ||
      TRIGGER_PROPS_SPREAD_RE.test(tag);
    if (wired) continue;

    const line = lineAt(processed, match.index);
    violations.push({ line, snippet: tag.replace(/\s+/g, " ").trim().slice(0, 160) });
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

// Forme de l'allowlist : un tableau de { file, line, reason } — granularité
// par LIGNE (pas par fichier entier, contrairement à
// i18n-coverage-allowlist.json, aujourd'hui vide) : plusieurs fichiers
// trouvés à la clôture de cette tâche (CollectionsAdminPage.tsx,
// RolesAdminPage.tsx) câblent déjà correctement usePanelTrigger() sur
// certains de leurs déclencheurs et pas sur d'autres — une exemption au
// fichier entier aurait rendu invisible toute régression future sur les
// déclencheurs déjà corrects du même fichier. Contrepartie assumée : un
// futur commit qui déplace des lignes dans un fichier déjà partiellement
// listé peut faire réapparaître une entrée comme "nouvelle" (le couple
// file:line ne correspond plus) sans qu'aucun trigger n'ait réellement
// changé — c'est voulu (force une revue humaine plutôt que de se fier
// silencieusement à un numéro de ligne périmé), mais ça a un coût de
// maintenance. `reason` est obligatoire : une entrée sans justification
// est refusée (n'exempte rien), pour qu'un futur ajout ne puisse jamais se
// contenter d'un couple nu sans explication.
function loadAllowlist(path) {
  if (!path || !existsSync(path)) return new Set();
  try {
    const raw = JSON.parse(readFileSync(path, "utf-8"));
    const keys = new Set();
    for (const entry of raw) {
      if (
        !entry ||
        typeof entry.file !== "string" ||
        typeof entry.line !== "number" ||
        !entry.reason
      ) {
        throw new Error(
          `entrée d'allowlist sans "file"/"line"/"reason" valides : ${JSON.stringify(entry)}`,
        );
      }
      keys.add(`${entry.file}:${entry.line}`);
    }
    return keys;
  } catch (err) {
    console.error(`Allowlist illisible (${path}) : ${err.message}`);
    return new Set();
  }
}

/**
 * CLI : parcourt `targetDirs`, rapporte chaque violation ; sort en erreur
 * (exit 1) si une violation (file:line) n'est pas dans `allowlistPath`. Un
 * déclencheur déjà connu et documenté comme dette (REV-088, "jamais posé
 * rétroactivement") peut y figurer plutôt que de bloquer la CI, mais tout
 * NOUVEAU déclencheur qui introduirait la même omission après cette
 * clôture doit être corrigé, pas ajouté à cette liste.
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
    const relFile = relative(process.cwd(), file).replaceAll("\\", "/");
    for (const v of violations) {
      const excluded = allowlist.has(`${relFile}:${v.line}`);
      const prefix = excluded ? "(allowlist) " : "";
      console.log(`${prefix}${file}:${v.line}: ${v.snippet}`);
      violationCount += 1;
      if (!excluded) failing = true;
    }
  }

  if (failing) {
    console.error(
      `\nÉCHEC : déclencheur(s) de panneau sans aria-expanded/aria-controls hors allowlist ` +
        `(${violationCount} occurrence(s) au total, voir ci-dessus). Câbler usePanelTrigger() ` +
        `(shell/src/ui/kit/usePanelTrigger.ts) ou aria-expanded/aria-controls manuellement.`,
    );
    process.exit(1);
  }
  console.log(
    `OK : aucun déclencheur de panneau non câblé hors allowlist (${violationCount} en allowlist).`,
  );
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const defaultAllowlist = join(scriptDir, "aria-panel-coverage-allowlist.json");
  const args = process.argv.slice(2);
  const allowlistIdx = args.indexOf("--allowlist");
  let allowlistPath = defaultAllowlist;
  let dirs = args;
  if (allowlistIdx !== -1) {
    allowlistPath = args[allowlistIdx + 1];
    dirs = [...args.slice(0, allowlistIdx), ...args.slice(allowlistIdx + 2)];
  }
  dirs = dirs.map((d) => relative(process.cwd(), join(process.cwd(), d)));
  main(dirs, allowlistPath);
}
