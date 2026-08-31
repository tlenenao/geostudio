// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema } from "../../api/types";
import { FilterOperator, FilterRow } from "./compileFilter";
import { Button } from "../../ui/kit/Button";

const OPERATOR_LABELS: Record<FilterOperator, string> = {
  eq: "égal à",
  neq: "différent de",
  gt: "supérieur à",
  gte: "supérieur ou égal à",
  lt: "inférieur à",
  lte: "inférieur ou égal à",
  contains: "contient",
};

export function QueryFilterBuilder({
  schema,
  rows,
  onChange,
}: {
  schema: CollectionSchema;
  rows: FilterRow[];
  onChange: (rows: FilterRow[]) => void;
}) {
  function updateRow(index: number, patch: Partial<FilterRow>) {
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }
  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }
  function addRow() {
    onChange([...rows, { column: schema.fields[0]?.name ?? "", operator: "eq", value: "" }]);
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, i) => {
        const fieldType = schema.fields.find((f) => f.name === row.column)?.type;
        const isNumeric = fieldType === "integer" || fieldType === "number";
        return (
          <div key={i} className="flex items-center gap-2">
            <select
              aria-label={`Colonne du filtre ${i + 1}`}
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
              value={row.column}
              onChange={(e) => updateRow(i, { column: e.target.value })}
            >
              {schema.fields.map((f) => (
                <option key={f.name} value={f.name}>
                  {f.name}
                </option>
              ))}
            </select>
            <select
              aria-label={`Opérateur du filtre ${i + 1}`}
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
              value={row.operator}
              onChange={(e) => updateRow(i, { operator: e.target.value as FilterOperator })}
            >
              {Object.entries(OPERATOR_LABELS).map(([op, label]) => (
                <option key={op} value={op}>
                  {label}
                </option>
              ))}
            </select>
            <input
              aria-label={`Valeur du filtre ${i + 1}`}
              inputMode={isNumeric ? "numeric" : undefined}
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
              value={row.value}
              onChange={(e) => updateRow(i, { value: e.target.value })}
            />
            <button
              type="button"
              aria-label={`Supprimer le filtre ${i + 1}`}
              className="text-xs text-danger"
              onClick={() => removeRow(i)}
            >
              Supprimer
            </button>
          </div>
        );
      })}
      <Button type="button" size="sm" variant="outline" onClick={addRow}>
        Ajouter un filtre
      </Button>
    </div>
  );
}
