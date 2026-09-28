// SPDX-License-Identifier: Apache-2.0

// D35 (Vague C, SP-C6) : mise en forme visuelle des messages d'erreur
// `cel-js` (via `validateExpression` dans expr.ts) — pas de traduction
// technique, le contenu de chaque message reste tel quel. `cel-js` concatène
// plusieurs erreurs de parsing avec "; " ; un message par ligne, préfixé,
// est plus lisible qu'un unique bloc de prose.
export function formatCelError(raw: string): string {
  return raw
    .split("; ")
    .map((part) => `• ${part}`)
    .join("\n");
}
