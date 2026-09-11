// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { applyVisualQueryClientOp } from "./applyVisualQueryClientOp";

function setters() {
  return { setFilters: vi.fn(), setJoin: vi.fn(), setSummary: vi.fn() };
}

describe("applyVisualQueryClientOp", () => {
  it("applies a valid filters array", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { filters: [{ column: "titre", operator: "eq", value: "x" }] },
      },
      s,
    );
    expect(s.setFilters).toHaveBeenCalledWith([{ column: "titre", operator: "eq", value: "x" }]);
    expect(s.setJoin).not.toHaveBeenCalled();
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("drops a filter row with an invalid operator", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { filters: [{ column: "titre", operator: "startswith", value: "x" }] },
      },
      s,
    );
    expect(s.setFilters).toHaveBeenCalledWith([]);
  });

  it("applies join:null", () => {
    const s = setters();
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { join: null } }, s);
    expect(s.setJoin).toHaveBeenCalledWith(null);
  });

  it("applies a valid join object", () => {
    const s = setters();
    const join = { collectionId: "communes", on: "code_insee", how: "inner" as const };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { join } }, s);
    expect(s.setJoin).toHaveBeenCalledWith(join);
  });

  it("ignores an invalid join object (missing fields)", () => {
    const s = setters();
    applyVisualQueryClientOp(
      { op: "applyVisualQueryDraft", args: { join: { collectionId: "communes" } } },
      s,
    );
    expect(s.setJoin).not.toHaveBeenCalled();
  });

  it("applies a valid summary object", () => {
    const s = setters();
    const summary = {
      groupBy: ["titre"],
      metrics: [{ alias: "total", function: "count" as const, sourceColumn: null, p: null }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s);
    expect(s.setSummary).toHaveBeenCalledWith(summary);
  });

  it("ignores a summary whose metric requires sourceColumn but omits it", () => {
    const s = setters();
    const summary = {
      groupBy: ["titre"],
      // "sum" requires a non-null sourceColumn (metricExpr quoteIdent's it) —
      // this metric is schema-conformant (alias/function both valid) but
      // omits the field entirely.
      metrics: [{ alias: "total_pop", function: "sum" as const }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose metric has sourceColumn: null for a function that needs one", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [{ alias: "avg_pop", function: "avg" as const, sourceColumn: null, p: null }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose percentile metric is missing p", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [{ alias: "p90", function: "percentile" as const, sourceColumn: "population" }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose percentile metric has a non-numeric p", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [
        { alias: "p90", function: "percentile" as const, sourceColumn: "population", p: "90" },
      ],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose percentile metric has p out of the (0, 100) range", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [
        { alias: "p90", function: "percentile" as const, sourceColumn: "population", p: 150 },
      ],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("applies a valid summary with a count metric and sourceColumn: null", () => {
    // "count" compiles to count(*) (compilePipeline.ts::metricExpr) and never
    // reads sourceColumn — the round-trip contract with decompileMetrics is
    // that count's sourceColumn is always exactly null.
    const s = setters();
    const summary = {
      groupBy: ["titre"],
      metrics: [{ alias: "n", function: "count" as const, sourceColumn: null, p: null }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s);
    expect(s.setSummary).toHaveBeenCalledWith(summary);
  });

  it("ignores an unknown op", () => {
    const s = setters();
    applyVisualQueryClientOp({ op: "somethingElse", args: {} }, s);
    expect(s.setFilters).not.toHaveBeenCalled();
    expect(s.setJoin).not.toHaveBeenCalled();
    expect(s.setSummary).not.toHaveBeenCalled();
  });
});
