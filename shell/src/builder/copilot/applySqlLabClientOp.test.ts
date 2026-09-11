// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { applySqlLabClientOp } from "./applySqlLabClientOp";

describe("applySqlLabClientOp", () => {
  it("sets the sql draft on applySqlDraft", () => {
    const setSql = vi.fn();
    applySqlLabClientOp({ op: "applySqlDraft", args: { sql: "SELECT 1" } }, setSql);
    expect(setSql).toHaveBeenCalledWith("SELECT 1");
  });

  it("ignores an unknown op", () => {
    const setSql = vi.fn();
    applySqlLabClientOp({ op: "somethingElse", args: {} }, setSql);
    expect(setSql).not.toHaveBeenCalled();
  });

  it("ignores an empty/blank sql", () => {
    const setSql = vi.fn();
    applySqlLabClientOp({ op: "applySqlDraft", args: { sql: "   " } }, setSql);
    expect(setSql).not.toHaveBeenCalled();
  });
});
