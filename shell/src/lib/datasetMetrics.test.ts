// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { resolveMetricMeasures } from "./datasetMetrics";

const metrics = { rec: { field: "montant", agg: "sum", label: "Recettes" } };

describe("resolveMetricMeasures", () => {
  it("remplace la mesure par la métrique, libellé de ligne = clé", () => {
    const out = resolveMetricMeasures(
      { groupBy: "commune", measures: [{ metric: "rec" }, { agg: "count", label: "n" }] },
      metrics,
    );
    expect(out.measures).toEqual([
      { field: "montant", agg: "sum", p: undefined, label: "rec" },
      { agg: "count", label: "n" },
    ]);
  });
  it("conserve un libellé explicite", () => {
    const out = resolveMetricMeasures({ measures: [{ metric: "rec", label: "x" }] }, metrics);
    expect((out.measures as { label: string }[])[0].label).toBe("x");
  });
  it("refuse une métrique inconnue", () => {
    expect(() => resolveMetricMeasures({ measures: [{ metric: "zz" }] }, metrics)).toThrow(
      /unknown metric/,
    );
  });
  it("laisse intacte une requête sans métrique", () => {
    const q = { agg: "count" };
    expect(resolveMetricMeasures(q, undefined)).toBe(q);
  });
});
