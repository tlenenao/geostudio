// SPDX-License-Identifier: Apache-2.0
import { evaluateExpression, type ExprContext } from "../builder/expr";
import { sanitizeMarkdown } from "../builder/widgets/sanitizeMarkdown";

// Le gabarit de popup (SP-24 §3.5) est du markdown où chaque ${expression} est
// évaluée en CEL. C'est la SECONDE syntaxe d'expression du dépôt, à côté du
// binding JSON { $expr } de builder/exprBindings.ts — divergence assumée par la
// spec : c'est la seule forme qui donne une mise en forme libre.
//
// Deux règles non négociables :
//  - un placeholder mal formé ou une expression invalide ne lève jamais ;
//  - on interpole d'abord et on assainit ensuite (renderPopupTemplate), donc
//    une valeur de propriété est traitée comme du markdown et DOMPurify est
//    ce qui rend l'opération sûre.

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// Index du "}" fermant le "${" ouvert à `start`, en comptant la profondeur —
// une expression CEL peut contenir un littéral de map ({'a': 1}). -1 si le
// placeholder n'est jamais fermé.
function closingBrace(template: string, start: number): number {
  let depth = 0;
  for (let i = start + 2; i < template.length; i += 1) {
    const ch = template[i];
    if (ch === "{") depth += 1;
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
