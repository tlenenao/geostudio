// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema, CollectionSchemaField, DatasetColumnMeta } from "../api/types";

export type MergedSchemaField = CollectionSchemaField & DatasetColumnMeta;

export function mergeDatasetSchema(
  schema: CollectionSchema,
  columns: Record<string, DatasetColumnMeta>,
): MergedSchemaField[] {
  return schema.fields
    .filter((field) => field.type !== "attachment")
    .map((field) => ({ ...field, ...columns[field.name] }));
}
