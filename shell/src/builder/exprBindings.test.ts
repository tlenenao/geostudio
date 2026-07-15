// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { resolveExprBindings } from "./exprBindings";

const ctx = { vars: { seuil: "haute" }, record: { nom: "A" }, user: { name: "tanguy" } };

test("returns a primitive unchanged", () => {
  expect(resolveExprBindings("hello", ctx)).toBe("hello");
  expect(resolveExprBindings(42, ctx)).toBe(42);
  expect(resolveExprBindings(null, ctx)).toBe(null);
  expect(resolveExprBindings(undefined, ctx)).toBe(undefined);
});

test("replaces an { $expr } object with its evaluated value", () => {
  expect(resolveExprBindings({ $expr: "1 + 2" }, ctx)).toBe(3);
  expect(resolveExprBindings({ $expr: "vars.seuil" }, ctx)).toBe("haute");
});

test("does not treat an object with extra keys alongside $expr as a binding", () => {
  const value = { $expr: "1 + 2", label: "x" };
  expect(resolveExprBindings(value, ctx)).toEqual({ $expr: "1 + 2", label: "x" });
});

test("recurses into arrays, resolving each element", () => {
  expect(resolveExprBindings([{ $expr: "1 + 1" }, "plain", { $expr: "2 + 2" }], ctx)).toEqual([2, "plain", 4]);
});

test("recurses into nested plain objects", () => {
  const value = { a: { b: { $expr: "vars.seuil" } }, c: "d" };
  expect(resolveExprBindings(value, ctx)).toEqual({ a: { b: "haute" }, c: "d" });
});

test("does not treat a calculated-column object ({ label, expr }) as a binding", () => {
  const value = { label: "C", expr: "1 + 1" };
  expect(resolveExprBindings(value, ctx)).toEqual({ label: "C", expr: "1 + 1" });
});

test("never throws on an invalid expression, propagating undefined like any other value", () => {
  const value = { a: { $expr: "vars.seuil ==" } };
  expect(() => resolveExprBindings(value, ctx)).not.toThrow();
  expect(resolveExprBindings(value, ctx)).toEqual({ a: undefined });
});
