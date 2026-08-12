import { describe, expect, test } from "vitest";
import type { CollectionSchema } from "../../api/types";
import { compileFilterRowsToSql, decompileSqlToFilterRows } from "./compileFilter";

const SCHEMA: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [
    { name: "commune", type: "string", required: true },
    { name: "gravite", type: "integer", required: false },
    { name: "actif", type: "boolean", required: false },
  ],
};

describe("compileFilterRowsToSql", () => {
  test("une ligne = une comparaison quotée", () => {
    const sql = compileFilterRowsToSql([{ column: "gravite", operator: "gt", value: "3" }], SCHEMA);
    expect(sql).toBe('"gravite" > 3');
  });

  test("plusieurs lignes combinées en ET", () => {
    const sql = compileFilterRowsToSql(
      [
        { column: "commune", operator: "eq", value: "Paris" },
        { column: "actif", operator: "eq", value: "true" },
      ],
      SCHEMA,
    );
    expect(sql).toBe('"commune" = \'Paris\' AND "actif" = TRUE');
  });

  test("échappe les apostrophes dans une valeur texte", () => {
    const sql = compileFilterRowsToSql([{ column: "commune", operator: "eq", value: "L'Île" }], SCHEMA);
    expect(sql).toBe('"commune" = \'L\'\'Île\'');
  });

  test("contains produit un LIKE encadré de %", () => {
    const sql = compileFilterRowsToSql([{ column: "commune", operator: "contains", value: "par" }], SCHEMA);
    expect(sql).toBe('"commune" LIKE \'%par%\'');
  });
});

describe("decompileSqlToFilterRows", () => {
  test("round-trip sur une expression simple", () => {
    const original = [{ column: "gravite", operator: "gt" as const, value: "3" }];
    expect(decompileSqlToFilterRows(compileFilterRowsToSql(original, SCHEMA))).toEqual(original);
  });

  test("round-trip sur plusieurs lignes ET", () => {
    const original = [
      { column: "commune", operator: "eq" as const, value: "Paris" },
      { column: "actif", operator: "eq" as const, value: "true" },
    ];
    expect(decompileSqlToFilterRows(compileFilterRowsToSql(original, SCHEMA))).toEqual(original);
  });

  test("round-trip sur contains", () => {
    const original = [{ column: "commune", operator: "contains" as const, value: "par" }];
    expect(decompileSqlToFilterRows(compileFilterRowsToSql(original, SCHEMA))).toEqual(original);
  });

  test("chaîne vide -> aucune ligne", () => {
    expect(decompileSqlToFilterRows("")).toEqual([]);
  });

  test("forme non reconnue -> null (repli attendu vers le canvas complet)", () => {
    expect(decompileSqlToFilterRows("length(\"commune\") > 3")).toBeNull();
  });

  test("limite documentée : une valeur contenant littéralement ' AND ' casse le round-trip proprement (renvoie null, pas un crash)", () => {
    const sql = compileFilterRowsToSql([{ column: "commune", operator: "eq", value: "ROCK AND ROLL" }], SCHEMA);
    // Ambigu avec un split naïf sur " AND " — comportement documenté et
    // accepté : renvoie null (repli vers le canvas), jamais une exception ni
    // un résultat silencieusement faux.
    expect(decompileSqlToFilterRows(sql)).toBeNull();
  });
});
