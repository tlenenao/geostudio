// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test } from "vitest";
import type { CollectionSchema } from "../../api/types";
import { inferOutputColumns } from "./inferSchema";

const BASE: CollectionSchema = {
  collection: "incidents",
  pk: "id",
  geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [
    { name: "commune", type: "string", required: true },
    { name: "gravite", type: "integer", required: false },
    { name: "signale_le", type: "datetime", required: false },
  ],
};

const JOINED: CollectionSchema = {
  collection: "communes",
  pk: "id",
  geometry: null,
  fields: [
    { name: "commune", type: "string", required: true }, // colonne de jointure
    { name: "population", type: "integer", required: false },
    { name: "gravite", type: "string", required: false }, // collision de nom avec BASE, type différent
  ],
};

describe("inferOutputColumns", () => {
  test("passthrough : reprend toutes les colonnes de base avec la géométrie de base", () => {
    const result = inferOutputColumns(BASE, null, null, null);
    expect(result.columns).toEqual([
      { name: "commune", sqlType: "text" },
      { name: "gravite", sqlType: "integer" },
      { name: "signale_le", sqlType: "timestamptz" },
    ]);
    expect(result.geometryType).toBe("Point");
    expect(result.srid).toBe(4326);
  });

  test("jointure : renomme la colonne jointe en collision, jamais la colonne de jointure elle-même", () => {
    const join = { collectionId: "communes", on: "commune", how: "inner" as const };
    const result = inferOutputColumns(BASE, join, JOINED, null);
    const names = result.columns.map((c) => c.name);
    expect(names).toContain("commune"); // colonne de jointure, une seule fois
    expect(names).toContain("population"); // pas de collision, nom inchangé
    expect(names).toContain("gravite"); // colonne de base, jamais renommée ni supprimée
    expect(names).toContain("joined_gravite"); // collision : seule la colonne jointe est renommée
  });

  test("résumé : count -> integer, sum/avg -> double precision, aucune géométrie", () => {
    const summary = {
      groupBy: ["commune"],
      metrics: [
        { alias: "nb", function: "count" as const, sourceColumn: null },
        { alias: "total_gravite", function: "sum" as const, sourceColumn: "gravite" },
      ],
    };
    const result = inferOutputColumns(BASE, null, null, summary);
    expect(result.columns).toEqual([
      { name: "commune", sqlType: "text" },
      { name: "nb", sqlType: "integer" },
      { name: "total_gravite", sqlType: "double precision" },
    ]);
    expect(result.geometryType).toBeNull();
  });

  test("colonne de type unsupported est exclue silencieusement", () => {
    const withUnsupported: CollectionSchema = {
      ...BASE,
      fields: [...BASE.fields, { name: "brut", type: "unsupported", required: false }],
    };
    const result = inferOutputColumns(withUnsupported, null, null, null);
    expect(result.columns.map((c) => c.name)).not.toContain("brut");
  });
});
