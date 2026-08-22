// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from "vitest";
import { interpolatePopupTemplate, renderPopupTemplate } from "./popupTemplate";

const ctx = (record: Record<string, unknown>) => ({
  vars: {},
  user: { name: "t" },
  record,
});

test("interpolates a CEL placeholder against the clicked feature", () => {
  expect(interpolatePopupTemplate("## ${record.nom}", ctx({ nom: "Tulle" }))).toBe("## Tulle");
});

test("counts brace depth so a CEL map literal survives", () => {
  const out = interpolatePopupTemplate("${ {'a': 1}['a'] }", ctx({}));
  expect(out).toBe("1");
});

test("leaves an unclosed placeholder literal instead of throwing", () => {
  expect(interpolatePopupTemplate("nom: ${record.nom", ctx({ nom: "Tulle" }))).toBe(
    "nom: ${record.nom",
  );
});

test("renders an invalid expression as an empty string", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(interpolatePopupTemplate("[${(((}]", ctx({}))).toBe("[]");
  warn.mockRestore();
});

test("renders a missing field as an empty string", () => {
  expect(interpolatePopupTemplate("x${record.absent}y", ctx({}))).toBe("xy");
});

test("serializes an object value as JSON", () => {
  expect(interpolatePopupTemplate("${record.o}", ctx({ o: { a: 1 } }))).toBe('{"a":1}');
});

test("serializes an array value as JSON", () => {
  expect(interpolatePopupTemplate("${record.a}", ctx({ a: [1, "x", true] }))).toBe('[1,"x",true]');
});

test("degrades a circular object to a neutral placeholder instead of throwing", () => {
  const circ: Record<string, unknown> = {};
  circ.self = circ;
  expect(interpolatePopupTemplate("${record.self}", ctx({ self: circ }))).toBe("[objet]");
});

test("a CEL string literal containing a closing brace does not close the placeholder early", () => {
  expect(interpolatePopupTemplate('${ "}" }', ctx({}))).toBe("}");
});

test("a single-quoted CEL string literal containing a closing brace does not close the placeholder early", () => {
  expect(interpolatePopupTemplate("${ '}' }", ctx({}))).toBe("}");
});

test("an escaped quote inside a CEL string literal does not end the literal early", () => {
  // cel-js ne décode pas les séquences d'échappement (visitor.ts fait un simple
  // `.slice(1, -1)` sur l'image du token) : la barre oblique inverse survit
  // littéralement dans la valeur. Le point testé ici est que le scanner ne
  // referme pas le placeholder sur le "}" tout de suite après le "\"" échappé —
  // pas la décodification de l'échappement, qui n'est pas de son ressort.
  expect(interpolatePopupTemplate('${ "a\\"}" }', ctx({}))).toBe('a\\"}');
});

test("an unclosed placeholder earlier in the template swallows a later well-formed one literally", () => {
  // Comportement documenté et volontairement conservé (SP-24 Task 8, revue) :
  // laisser tout le reliquat littéral est plus sûr que d'évaluer un fragment
  // de gabarit tronqué en garbage CEL.
  expect(interpolatePopupTemplate("${oops ${record.nom} tail", ctx({ nom: "Tulle" }))).toBe(
    "${oops ${record.nom} tail",
  );
});

test("keeps several placeholders on one line", () => {
  expect(interpolatePopupTemplate("${record.a} / ${record.b}", ctx({ a: "x", b: "y" }))).toBe(
    "x / y",
  );
});

test("a template with no placeholder is returned unchanged", () => {
  expect(interpolatePopupTemplate("texte simple", ctx({}))).toBe("texte simple");
});

test("renderPopupTemplate turns markdown into html", () => {
  expect(renderPopupTemplate("## ${record.nom}", ctx({ nom: "Tulle" }))).toContain("Tulle");
  expect(renderPopupTemplate("## ${record.nom}", ctx({ nom: "Tulle" }))).toMatch(/<h2/);
});

test("renderPopupTemplate neutralizes html injected through a property value", () => {
  // La valeur vient de la donnée, potentiellement d'un tiers. On interpole
  // d'abord, on assainit ensuite : DOMPurify est la garantie (spec §3.5).
  const html = renderPopupTemplate("${record.nom}", ctx({ nom: '<img src=x onerror="alert(1)">' }));
  expect(html).not.toContain("onerror");
});

test("renderPopupTemplate strips a script tag injected through a property value", () => {
  const html = renderPopupTemplate("${record.nom}", ctx({ nom: "<script>alert(1)</script>" }));
  expect(html.toLowerCase()).not.toContain("<script");
});
