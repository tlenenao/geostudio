// SPDX-License-Identifier: Apache-2.0
import type { CollectionFieldType, CollectionSchema } from "../../api/types";

export type JoinConfig = { collectionId: string; on: string; how: "inner" | "left" };
export type MetricFunction = "count" | "sum" | "avg" | "min" | "max";
export type MetricConfig = { alias: string; function: MetricFunction; sourceColumn: string | null };
export type SummaryConfig = { groupBy: string[]; metrics: MetricConfig[] };

export type InferredColumn = { name: string; sqlType: string };
export type InferredSchema = { columns: InferredColumn[]; geometryType: string | null; srid: number | null };

// Aligné sur les 7 types SQL acceptés par EmptyCollectionColumn.sqlType côté
// cœur (core/app/collections/schemas.py) — "unsupported" n'a pas d'équivalent
// SQL sûr, la colonne est simplement exclue de la sortie.
const FIELD_TYPE_TO_SQL: Record<CollectionFieldType, string | null> = {
  string: "text", integer: "integer", number: "double precision",
  boolean: "boolean", date: "date", datetime: "timestamptz",
  enum: "text", unsupported: null,
};

function sqlTypeOf(schema: CollectionSchema, columnName: string): string {
  const field = schema.fields.find((f) => f.name === columnName);
  return (field && FIELD_TYPE_TO_SQL[field.type]) || "double precision";
}

export function inferOutputColumns(
  base: CollectionSchema, join: JoinConfig | null, joinedSchema: CollectionSchema | null,
  summary: SummaryConfig | null,
): InferredSchema {
  if (summary) {
    const columns: InferredColumn[] = [];
    for (const name of summary.groupBy) {
      const sqlType = sqlTypeOf(base, name);
      columns.push({ name, sqlType });
    }
    for (const metric of summary.metrics) {
      const sqlType =
        metric.function === "count" ? "integer"
        : metric.function === "sum" || metric.function === "avg" ? "double precision"
        : sqlTypeOf(base, metric.sourceColumn ?? "");
      columns.push({ name: metric.alias, sqlType });
    }
    // Un dataset résumé n'a pas de géométrie propre en v1 : un agrégat groupé
    // ne correspond à aucune géométrie individuelle sans jointure de retour
    // vers une couche de contour, hors périmètre de cet assistant.
    return { columns, geometryType: null, srid: null };
  }

  if (join && joinedSchema) {
    const baseNames = new Set(base.fields.map((f) => f.name));
    const joinedNames = new Set(joinedSchema.fields.map((f) => f.name).filter(n => n !== join.on));
    const columns: InferredColumn[] = [];

    // Add base fields, but skip those that collide with joined fields
    for (const f of base.fields) {
      if (joinedNames.has(f.name)) continue; // Skip if collides with joined field
      const sqlType = FIELD_TYPE_TO_SQL[f.type];
      if (sqlType) columns.push({ name: f.name, sqlType });
    }

    // Add joined fields
    for (const f of joinedSchema.fields) {
      if (f.name === join.on) continue; // dédupliquée par JOIN ... USING, déjà comptée côté base
      const sqlType = FIELD_TYPE_TO_SQL[f.type];
      if (!sqlType) continue;
      const outputName = baseNames.has(f.name) ? `joined_${f.name}` : f.name;
      columns.push({ name: outputName, sqlType });
    }
    return { columns, geometryType: base.geometry?.type ?? null, srid: base.geometry?.srid ?? null };
  }

  const columns: InferredColumn[] = [];
  for (const f of base.fields) {
    const sqlType = FIELD_TYPE_TO_SQL[f.type];
    if (sqlType) columns.push({ name: f.name, sqlType });
  }
  return { columns, geometryType: base.geometry?.type ?? null, srid: base.geometry?.srid ?? null };
}
