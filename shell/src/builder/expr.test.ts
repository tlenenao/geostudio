// SPDX-License-Identifier: Apache-2.0
import { afterEach, expect, test, vi } from "vitest";
import { evaluateExpression, validateExpression } from "./expr";

afterEach(() => vi.restoreAllMocks());

const ctx = { vars: { seuil: "haute" }, record: { gravite: "haute", titre: "Fuite" }, user: { name: "tanguy" } };

test("evaluates arithmetic, string concatenation and the ternary operator", () => {
  expect(evaluateExpression("1 + 2 * 3", ctx)).toBe(7);
  expect(evaluateExpression("'a' + 'b'", ctx)).toBe("ab");
  expect(evaluateExpression("1 == 1 ? 'oui' : 'non'", ctx)).toBe("oui");
});

test("resolves vars.x, record.champ and user.name", () => {
  expect(evaluateExpression("vars.seuil", ctx)).toBe("haute");
  expect(evaluateExpression("record.gravite == vars.seuil", ctx)).toBe(true);
  expect(evaluateExpression("user.name", ctx)).toBe("tanguy");
});

test("returns undefined (not throw) when the expression references a missing field", () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(evaluateExpression("record.missingField", ctx)).toBeUndefined();
  expect(console.warn).toHaveBeenCalled();
});

test("returns undefined (not throw) on a type mismatch", () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(evaluateExpression("record.titre > 5", ctx)).toBeUndefined();
});

test("validateExpression returns null for a syntactically valid expression", () => {
  expect(validateExpression("vars.seuil == 'haute'")).toBeNull();
});

test("validateExpression returns an error message for an invalid expression", () => {
  const err = validateExpression("vars.seuil ==");
  expect(err).not.toBeNull();
  expect(typeof err).toBe("string");
});

test("evaluateExpression can read the ctx.* analytics binding", () => {
  const result = evaluateExpression("ctx.timeRange.from", {
    vars: {}, user: { name: "" },
    ctx: { timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {} },
  });
  expect(result).toBe("2026-01-01");
});

test("evaluateExpression tolerates a missing ctx binding (no provider mounted)", () => {
  const result = evaluateExpression("vars.x", { vars: { x: 1 }, user: { name: "" } });
  expect(result).toBe(1);
});
