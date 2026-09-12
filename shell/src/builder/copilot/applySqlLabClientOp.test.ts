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

  // M1 (revue finale de branche GAP-17) : CopilotChat annonçait « Brouillon
  // SQL inséré. » même sur un op silencieusement abandonné.
  it("reports whether anything was actually applied", () => {
    expect(applySqlLabClientOp({ op: "applySqlDraft", args: { sql: "SELECT 1" } }, vi.fn())).toBe(
      true,
    );
    expect(applySqlLabClientOp({ op: "applySqlDraft", args: { sql: "  " } }, vi.fn())).toBe(false);
    expect(applySqlLabClientOp({ op: "somethingElse", args: {} }, vi.fn())).toBe(false);
  });
});
