// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { buildSqlLabClientToolSchemas } from "./sqlLabClientTools";

describe("buildSqlLabClientToolSchemas", () => {
  it("declares exactly one tool: applySqlDraft, requiring a sql string", () => {
    const schemas = buildSqlLabClientToolSchemas();
    expect(schemas).toHaveLength(1);
    expect(schemas[0].name).toBe("applySqlDraft");
    expect(schemas[0].inputSchema).toEqual({
      type: "object",
      properties: { sql: { type: "string", description: expect.any(String) } },
      required: ["sql"],
    });
  });
});
