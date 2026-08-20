// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { _resetRegistry } from "../registry";
import { registerBuiltinWidgets } from "../widgets";
import { buildClientToolSchemas } from "./clientTools";

describe("buildClientToolSchemas", () => {
  it("returns exactly the 5 client tools by name", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const names = buildClientToolSchemas().map((t) => t.name);
    expect(names).toEqual([
      "addWidget",
      "updateWidgetProps",
      "removeWidget",
      "addDataSource",
      "setFilter",
    ]);
  });

  it("addWidget's enum lists every registered widget type", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const addWidget = buildClientToolSchemas().find((t) => t.name === "addWidget")!;
    const enumValues = (addWidget.inputSchema as { properties: { type: { enum: string[] } } })
      .properties.type.enum;
    expect(enumValues).toContain("text");
    expect(enumValues).toContain("chart");
    expect(enumValues).toHaveLength(22);
  });

  it("updateWidgetProps' schema includes chart's scalar fields", () => {
    _resetRegistry();
    registerBuiltinWidgets();
    const updateProps = buildClientToolSchemas().find((t) => t.name === "updateWidgetProps")!;
    const props = (
      updateProps.inputSchema as { properties: { props: { properties: Record<string, unknown> } } }
    ).properties.props.properties;
    expect(props).toHaveProperty("chartType");
    expect(props).toHaveProperty("dataSourceId");
  });
});
