// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test } from "vitest";
import { parseDuckDbError } from "./parseDuckDbError";

describe("parseDuckDbError", () => {
  test("extrait catégorie/ligne/colonne d'un message DuckDB avec position", () => {
    const message =
      'Parser Error: syntax error at or near "fro"\n\nLINE 1: select * fro x\n                ^';
    const parsed = parseDuckDbError(message);
    expect(parsed.category).toBe("Parser Error");
    expect(parsed.message).toBe('syntax error at or near "fro"');
    expect(parsed.line).toBe(1);
    expect(parsed.column).toBe(17);
    expect(parsed.sqlSnippet).toBe("select * fro x");
  });

  test("retombe sur le message brut sans position (ex. erreur sans LINE)", () => {
    const message = "Parser Error: syntax error";
    const parsed = parseDuckDbError(message);
    expect(parsed.category).toBeNull();
    expect(parsed.message).toBe("Parser Error: syntax error");
    expect(parsed.line).toBeNull();
    expect(parsed.column).toBeNull();
    expect(parsed.sqlSnippet).toBeNull();
  });

  test("retombe sur le message brut si le format est totalement inattendu", () => {
    const parsed = parseDuckDbError("boom");
    expect(parsed).toEqual({
      category: null,
      message: "boom",
      line: null,
      column: null,
      sqlSnippet: null,
    });
  });
});
