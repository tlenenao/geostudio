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
