// SPDX-License-Identifier: Apache-2.0
import { marked } from "marked";
import DOMPurify from "dompurify";

// AUD-050 : tout lien rendu ouvre un nouvel onglet sans opener ni referrer.
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "A" && node.hasAttribute("href")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer");
  }
});

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// Single, non-bypassable path from author-supplied Markdown to inserted DOM:
// every RichSection render must go through this module, never call
// marked.parse directly — DOMPurify.sanitize is what makes the XSS risk
// (dangerouslySetInnerHTML downstream) acceptable.
export function sanitizeMarkdown(markdown: string): string {
  const html = marked.parse(markdown, { async: false }) as string;
  return DOMPurify.sanitize(html);
}

/** Gabarit d'auteur contenant des jetons `gspv<N>x` : le markdown est celui de
 * l'auteur seul ; chaque jeton devient la valeur échappée (texte ou attribut),
 * puis DOMPurify filtre le tout (schémas d'URL compris) — AUD-050. */
export function renderMarkdownWithValues(markdown: string, values: string[]): string {
  const html = marked.parse(markdown, { async: false }) as string;
  const filled = html.replace(/gspv(\d+)x/g, (_, i: string) => escapeHtml(values[Number(i)] ?? ""));
  return DOMPurify.sanitize(filled);
}
