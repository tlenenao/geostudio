// SPDX-License-Identifier: Apache-2.0
// AUD-051 : filtre par couche (clauses ET) compilé en expression MapLibre, posé sur les
// sous-couches de la couche sauf les clusters (leurs entités n'ont pas les propriétés source).
import type * as maplibregl from "maplibre-gl";
import type { LayerFilterClause } from "../api/types";

const OPS = { eq: "==", ne: "!=", gt: ">", gte: ">=", lt: "<", lte: "<=" } as const;

export function compileLayerFilter(clauses: LayerFilterClause[]): unknown[] | null {
  const exprs = clauses.map((c) => {
    const get = ["get", c.field];
    return c.op === "in" ? ["in", get, ["literal", c.value]] : [OPS[c.op], get, c.value];
  });
  return exprs.length === 0 ? null : ["all", ...exprs];
}

export function applyLayerFilter(
  map: maplibregl.Map,
  layer: { id: string; filter?: LayerFilterClause[] },
): void {
  const user = compileLayerFilter(layer.filter ?? []);
  if (!user) return;
  for (const sl of map.getStyle()?.layers ?? []) {
    if (sl.id !== layer.id && !sl.id.startsWith(`${layer.id}__`)) continue;
    if (sl.id.endsWith("__cluster") || sl.id.endsWith("__cluster_count")) continue;
    const base = map.getFilter(sl.id);
    map.setFilter(sl.id, (base ? ["all", base, user] : user) as maplibregl.FilterSpecification);
  }
}
