// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { buildVisualQueryClientToolSchemas } from "./visualQueryClientTools";

describe("buildVisualQueryClientToolSchemas", () => {
  it("declares exactly one tool: applyVisualQueryDraft", () => {
    const schemas = buildVisualQueryClientToolSchemas();
    expect(schemas).toHaveLength(1);
    expect(schemas[0].name).toBe("applyVisualQueryDraft");
    const props = schemas[0].inputSchema.properties as Record<string, unknown>;
    expect(Object.keys(props)).toEqual(["filters", "join", "summary"]);
  });
});
