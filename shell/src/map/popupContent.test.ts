// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { resolvePopupContent } from "./popupContent";

const ctx = { vars: {}, user: { name: "t" } };
const props = { id: 1, nom: "Tulle", population: 14000 };

test("without configuration every property becomes a row, in order", () => {
  const c = resolvePopupContent(undefined, props, ctx);
  expect(c.rows.map((r) => r.label)).toEqual(["id", "nom", "population"]);
  expect(c.rows.map((r) => r.value)).toEqual(["1", "Tulle", "14000"]);
  expect(c.title).toBeNull();
  expect(c.html).toBeNull();
});

test("the configured field list drives the order and the labels", () => {
  const c = resolvePopupContent(
    { titleField: "nom", fields: [{ name: "population", label: "Habitants" }, { name: "id" }] },
    props,
    ctx,
  );
  expect(c.title).toBe("Tulle");
  expect(c.rows).toEqual([
    { label: "Habitants", value: "14000" },
    { label: "id", value: "1" },
  ]);
});

test("a config without a fields key at all still falls back to every property", () => {
  const c = resolvePopupContent({ titleField: "nom" }, props, ctx);
  expect(c.title).toBe("Tulle");
  expect(c.rows.map((r) => r.label)).toEqual(["id", "population"]);
});

test("an empty fields array means no field at all, not a fallback to every property", () => {
  const c = resolvePopupContent(
    { titleField: "nom", fields: [] },
    { id: 1, nom: "Tulle", population: 14000, internal_secret_code: "XYZ" },
    ctx,
  );
  expect(c.title).toBe("Tulle");
  expect(c.rows).toEqual([]);
});

test("a configured field absent from the properties is dropped, not rendered empty", () => {
  const c = resolvePopupContent({ fields: [{ name: "absent" }, { name: "nom" }] }, props, ctx);
  expect(c.rows).toEqual([{ label: "nom", value: "Tulle" }]);
});

test("a non-empty template wins over titleField and fields", () => {
  const c = resolvePopupContent(
    { titleField: "nom", fields: [{ name: "id" }], template: "**${record.nom}**" },
    props,
    ctx,
  );
  expect(c.rows).toEqual([]);
  expect(c.title).toBeNull();
  expect(c.html).toContain("Tulle");
});

test("an empty or blank template falls back to the field list", () => {
  const c = resolvePopupContent({ fields: [{ name: "nom" }], template: "   " }, props, ctx);
  expect(c.html).toBeNull();
  expect(c.rows).toEqual([{ label: "nom", value: "Tulle" }]);
});

test('a null property value renders as an em dash, never as "null"', () => {
  const c = resolvePopupContent({ fields: [{ name: "nom" }] }, { nom: null }, ctx);
  expect(c.rows).toEqual([{ label: "nom", value: "—" }]);
});

test("a circular object property degrades to a neutral placeholder instead of throwing", () => {
  const circular: Record<string, unknown> = {};
  circular.self = circular;
  expect(() =>
    resolvePopupContent({ fields: [{ name: "circular" }] }, { circular }, ctx),
  ).not.toThrow();
  const c = resolvePopupContent({ fields: [{ name: "circular" }] }, { circular }, ctx);
  expect(c.rows).toEqual([{ label: "circular", value: "[objet]" }]);
});
