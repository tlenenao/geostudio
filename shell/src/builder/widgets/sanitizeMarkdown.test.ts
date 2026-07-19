// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { sanitizeMarkdown } from "./sanitizeMarkdown";

test("renders CommonMark: headings, bold/italic, links, lists", () => {
  const html = sanitizeMarkdown("# Titre\n\n**gras** et *italique*\n\n- un\n- deux\n\n[lien](https://example.com)");
  expect(html).toContain("<h1>Titre</h1>");
  expect(html).toContain("<strong>gras</strong>");
  expect(html).toContain("<em>italique</em>");
  expect(html).toContain("<li>un</li>");
  expect(html).toContain('href="https://example.com"');
});

test("strips <script> tags", () => {
  const html = sanitizeMarkdown("# Titre\n\n<script>alert(1)</script>");
  expect(html).not.toContain("<script");
  expect(html).not.toContain("alert(1)");
});

test("strips onerror/on* event handler attributes", () => {
  const html = sanitizeMarkdown('<img src="x" onerror="alert(2)">');
  expect(html).not.toContain("onerror");
});

test("strips javascript: hrefs", () => {
  const html = sanitizeMarkdown("[lien](javascript:alert(3))");
  expect(html).not.toContain("javascript:");
});
