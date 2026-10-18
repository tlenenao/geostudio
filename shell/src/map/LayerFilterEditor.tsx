// SPDX-License-Identifier: Apache-2.0
// AUD-051 : éditeur du filtre par couche (clauses ET : champ, opérateur, valeur).
import type { LayerFilterClause, MapLayer } from "../api/types";
import { t } from "../i18n";
import "../i18n/domains/map";

type Scalar = string | number | boolean;
const OPS: LayerFilterClause["op"][] = ["eq", "ne", "gt", "gte", "lt", "lte", "in"];
const scalar = (v: string): Scalar => (v.trim() !== "" && !isNaN(Number(v)) ? Number(v) : v);

export function parseFilterValue(
  op: LayerFilterClause["op"],
  raw: string,
): LayerFilterClause["value"] {
  return op === "in" ? raw.split(",").map((x) => scalar(x.trim())) : scalar(raw);
}
const show = (v: LayerFilterClause["value"]) => (Array.isArray(v) ? v.join(",") : String(v));

export function LayerFilterEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const clauses = layer.filter ?? [];
  const commit = (next: LayerFilterClause[]) => {
    const { filter: _drop, ...rest } = layer;
    onChangeLayer(next.length ? { ...rest, filter: next } : rest);
  };
  const patch = (i: number, p: Partial<LayerFilterClause>) =>
    commit(clauses.map((c, j) => (j === i ? ({ ...c, ...p } as LayerFilterClause) : c)));
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="text-xs font-medium">{t("layersPanel.filter")}</legend>
      {clauses.map((c, i) => (
        <div key={i} className="flex flex-wrap items-center gap-1 text-xs">
          <input
            aria-label={t("layersPanel.filterField")}
            className="h-9 w-28 rounded border border-rule bg-surface px-1"
            value={c.field}
            onChange={(e) => patch(i, { field: e.target.value })}
          />
          <select
            aria-label={t("layersPanel.filterOp")}
            className="h-9 rounded border border-rule bg-surface px-1"
            value={c.op}
            onChange={(e) => {
              const op = e.target.value as LayerFilterClause["op"];
              patch(i, { op, value: parseFilterValue(op, show(c.value)) });
            }}
          >
            {OPS.map((o) => (
              <option key={o} value={o}>
                {t(`layersPanel.filterOp.${o}`)}
              </option>
            ))}
          </select>
          <input
            aria-label={t("layersPanel.filterValue")}
            className="h-9 w-28 rounded border border-rule bg-surface px-1"
            defaultValue={show(c.value)}
            onBlur={(e) => patch(i, { value: parseFilterValue(c.op, e.target.value) })}
          />
          <button
            type="button"
            aria-label={t("layersPanel.filterRemove")}
            onClick={() => commit(clauses.filter((_, j) => j !== i))}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        className="self-start text-xs underline"
        onClick={() => commit([...clauses, { field: "", op: "eq", value: "" }])}
      >
        {t("layersPanel.filterAdd")}
      </button>
    </fieldset>
  );
}
