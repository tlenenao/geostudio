// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, beforeEach } from "vitest";
import type { AppConfig } from "../../api/types";
import { _resetRegistry } from "../registry";
import { registerBuiltinWidgets } from "../widgets";
import { applyClientOp } from "./applyClientOp";

function emptyConfig(): AppConfig {
  return {
    kind: "app",
    theme: {} as AppConfig["theme"],
    dataSources: [],
    messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
  };
}

describe("applyClientOp", () => {
  beforeEach(() => {
    _resetRegistry();
    registerBuiltinWidgets();
  });

  it("addWidget adds an item with the widget's default props/size", () => {
    const config = applyClientOp(
      { op: "addWidget", args: { type: "text" } },
      emptyConfig(),
      "page-1",
    );
    expect(config.layout.items).toHaveLength(1);
    expect(config.layout.items[0].widget).toBe("text");
    expect(config.layout.items[0].props).toEqual({ text: "Nouveau texte", dataSourceId: "" });
  });

  it("addWidget with an unknown type is a no-op", () => {
    const config = applyClientOp(
      { op: "addWidget", args: { type: "not-a-real-widget" } },
      emptyConfig(),
      "page-1",
    );
    expect(config.layout.items).toHaveLength(0);
  });

  it("updateWidgetProps merges only keys present in configSchema, coerced by type", () => {
    let config = applyClientOp(
      { op: "addWidget", args: { type: "indicator" } },
      emptyConfig(),
      "page-1",
    );
    const widgetId = config.layout.items[0].id;
    config = applyClientOp(
      {
        op: "updateWidgetProps",
        args: { widgetId, props: { label: "Incidents ouverts", agg: 42, notARealProp: "x" } },
      },
      config,
      "page-1",
    );
    expect(config.layout.items[0].props).toEqual({
      dataSourceId: "",
      label: "Incidents ouverts",
      agg: "42",
      field: "",
    });
  });

  it("removeWidget removes the item by id", () => {
    let config = applyClientOp(
      { op: "addWidget", args: { type: "text" } },
      emptyConfig(),
      "page-1",
    );
    const widgetId = config.layout.items[0].id;
    config = applyClientOp({ op: "removeWidget", args: { widgetId } }, config, "page-1");
    expect(config.layout.items).toHaveLength(0);
  });

  it("addDataSource appends a new source, ignoring a duplicate id", () => {
    let config = applyClientOp(
      {
        op: "addDataSource",
        args: { id: "ds1", type: "features", service: "ogc", layer: "incidents" },
      },
      emptyConfig(),
      "page-1",
    );
    expect(config.dataSources).toEqual([
      { id: "ds1", type: "features", service: "ogc", layer: "incidents", query: {} },
    ]);
    config = applyClientOp(
      {
        op: "addDataSource",
        args: { id: "ds1", type: "features", service: "ogc", layer: "other" },
      },
      config,
      "page-1",
    );
    expect(config.dataSources).toHaveLength(1); // duplicate id ignored
  });

  it("setFilter updates an existing source's query", () => {
    let config = applyClientOp(
      {
        op: "addDataSource",
        args: { id: "ds1", type: "features", service: "ogc", layer: "incidents" },
      },
      emptyConfig(),
      "page-1",
    );
    config = applyClientOp(
      { op: "setFilter", args: { dataSourceId: "ds1", query: { status: "open" } } },
      config,
      "page-1",
    );
    expect(config.dataSources[0].query).toEqual({ status: "open" });
  });

  it("an unknown op name is a no-op, never throws", () => {
    const config = emptyConfig();
    const result = applyClientOp({ op: "deleteEverything", args: {} }, config, "page-1");
    expect(result).toBe(config);
  });
});
