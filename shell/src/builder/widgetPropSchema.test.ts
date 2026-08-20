// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { _resetRegistry, listWidgets } from "./registry";
import { registerBuiltinWidgets } from "./widgets";

describe("configSchema", () => {
  it("every builtin widget declares a configSchema (possibly empty)", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    for (const w of listWidgets()) {
      expect(w.configSchema, `widget "${w.type}" has no configSchema`).toBeDefined();
    }
  });

  it("text widget's configSchema matches its scalar defaultProps", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const text = listWidgets().find((w) => w.type === "text");
    expect(text?.configSchema).toEqual([
      { name: "text", type: "string", label: "Texte", default: "Nouveau texte" },
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
    ]);
  });

  it("chart widget's configSchema covers all 15 scalar props", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const chart = listWidgets().find((w) => w.type === "chart");
    expect(chart?.configSchema).toHaveLength(15);
    expect(chart?.configSchema?.map((p) => p.name)).toContain("chartType");
  });

  it("tabs widget has an empty configSchema (its only prop, `tabs`, is array-shaped, out of scope for v1)", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const tabs = listWidgets().find((w) => w.type === "tabs");
    expect(tabs?.configSchema).toEqual([]);
  });
});
