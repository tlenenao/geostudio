// SPDX-License-Identifier: Apache-2.0
import { marked } from "marked";
import DOMPurify from "dompurify";

// Single, non-bypassable path from author-supplied Markdown to inserted DOM:
// every RichSection render must go through this function, never call
// marked.parse directly — DOMPurify.sanitize is what makes the XSS risk
// (dangerouslySetInnerHTML downstream) acceptable.
export function sanitizeMarkdown(markdown: string): string {
  const html = marked.parse(markdown, { async: false }) as string;
  return DOMPurify.sanitize(html);
}
