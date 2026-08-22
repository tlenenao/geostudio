// SPDX-License-Identifier: Apache-2.0
import { evaluateExpression, type ExprContext } from "../builder/expr";
import { sanitizeMarkdown } from "../builder/widgets/sanitizeMarkdown";

// Le gabarit de popup (SP-24 §3.5) est du markdown où chaque ${expression} est
// évaluée en CEL. C'est la SECONDE syntaxe d'expression du dépôt, à côté du
// binding JSON { $expr } de builder/exprBindings.ts — divergence assumée par la
// spec : c'est la seule forme qui donne une mise en forme libre.
//
// Deux règles non négociables, y compris pour un résultat non sérialisable
// (structure circulaire, BigInt…) et pour un placeholder dont l'expression
// contient elle-même un "}" entre guillemets :
//  - un placeholder mal formé ou une expression invalide ne lève jamais ;
//  - on interpole d'abord et on assainit ensuite (renderPopupTemplate), donc
//    une valeur de propriété est traitée comme du markdown et DOMPurify est
//    ce qui rend l'opération sûre.

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      // Structure circulaire (ex. record.self = record) ou toute autre valeur
      // que JSON.stringify refuse (BigInt imbriqué…) : on dégrade vers un
      // texte neutre plutôt que de laisser l'exception remonter. Délibérément
      // PAS une chaîne vide : "" signifie déjà "champ absent/null" ailleurs
      // dans ce module (cf. tests), et confondre les deux cacherait qu'une
      // valeur existait bel et bien mais n'a pas pu être affichée.
      return "[objet]";
    }
  }
  return String(value);
}

// Index du "}" fermant le "${" ouvert à `start`, en comptant la profondeur —
// une expression CEL peut contenir un littéral de map ({'a': 1}) — et en
// ignorant tout "{"/"}" à l'intérieur d'un littéral de chaîne CEL, simple ou
// double guillemet avec échappement par barre oblique inverse (cel-js,
// tokens.ts : /(?:"(?:[^"\n\\]|\\.)*")|(?:'(?:[^'\n\\]|\\.)*')/) — sans quoi
// une expression telle que `"}"` referme le placeholder trop tôt et laisse
// fuiter le reste littéralement. Ce n'est pas un parseur CEL complet : on ne
// fait que sauter les littéraux de chaîne pour trouver la bonne accolade
// fermante, rien de plus. -1 si le placeholder n'est jamais fermé (y compris
// une chaîne elle-même non refermée avant la fin du gabarit) — le gabarit
// entier à partir de `start` est alors laissé littéral par l'appelant, qui
// avale aussi tout placeholder ${...} imbriqué plus loin dans ce reliquat
// (cf. test "un ${ non fermé avale un placeholder bien formé plus loin").
function closingBrace(template: string, start: number): number {
  let depth = 0;
  let quote: '"' | "'" | null = null;
  for (let i = start + 2; i < template.length; i += 1) {
    const ch = template[i];
    if (quote !== null) {
      if (ch === "\\") {
        i += 1; // barre oblique inverse : le caractère suivant est échappé, jamais un guillemet fermant.
      } else if (ch === quote) {
        quote = null;
      }
      continue;
    }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "{") depth += 1;
    else if (ch === "}") {
      if (depth === 0) return i;
      depth -= 1;
    }
  }
  return -1;
}

export function interpolatePopupTemplate(template: string, ctx: ExprContext): string {
  let out = "";
  let i = 0;
  while (i < template.length) {
    const open = template.indexOf("${", i);
    if (open === -1) {
      out += template.slice(i);
      break;
    }
    const close = closingBrace(template, open);
    if (close === -1) {
      // Placeholder non fermé : le reste du gabarit est laissé littéral.
      out += template.slice(i);
      break;
    }
    out += template.slice(i, open);
    out += stringify(evaluateExpression(template.slice(open + 2, close).trim(), ctx));
    i = close + 1;
  }
  return out;
}

export function renderPopupTemplate(template: string, ctx: ExprContext): string {
  return sanitizeMarkdown(interpolatePopupTemplate(template, ctx));
}
