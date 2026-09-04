// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test } from "vitest";
import { mergeDatasetSchema } from "./datasetSchema";
import type { CollectionSchema } from "../api/types";

const schema: CollectionSchema = {
  collection: "parcs",
  pk: "id",
  geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [
    { name: "nom", type: "string", required: true },
    { name: "surface", type: "number", required: false },
  ],
};

describe("mergeDatasetSchema", () => {
  test("merges column overrides onto the introspected fields, in schema order", () => {
    const merged = mergeDatasetSchema(schema, { nom: { label: "Nom du parc", format: "text" } });
    expect(merged).toEqual([
      { name: "nom", type: "string", required: true, label: "Nom du parc", format: "text" },
      { name: "surface", type: "number", required: false },
    ]);
  });

  test("fields without an override keep only their introspected properties", () => {
    const merged = mergeDatasetSchema(schema, {});
    expect(merged).toEqual(schema.fields);
  });

  test("an override for a column no longer in the schema is silently dropped", () => {
    const merged = mergeDatasetSchema(schema, { disparue: { label: "Fantôme" } });
    expect(merged.find((f) => f.name === "disparue")).toBeUndefined();
  });

  test("un pseudo-champ attachment n'a pas de colonne réelle : jamais mergé (revue finale, I3)", () => {
    const schemaWithAttachment: CollectionSchema = {
      ...schema,
      fields: [...schema.fields, { name: "photos", type: "attachment", required: false }],
    };
    const merged = mergeDatasetSchema(schemaWithAttachment, {});
    expect(merged.find((f) => f.name === "photos")).toBeUndefined();
    expect(merged).toHaveLength(2);
  });
});
