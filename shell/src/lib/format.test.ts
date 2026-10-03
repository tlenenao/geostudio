// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { formatDateTime, formatNumber } from "./format";

describe("format fr-FR", () => {
  it("formate une date en jj/mm/aaaa", () => {
    expect(formatDateTime("2026-09-30T04:52:57")).toMatch(/^30\/09\/2026 04:52:57$/);
    expect(formatDateTime("n'importe quoi")).toBe("n'importe quoi");
  });
  it("formate les nombres avec virgule et séparateur de milliers", () => {
    expect(formatNumber(1234567.75).replace(/\s/g, " ")).toBe("1 234 567,75");
    expect(formatNumber(12.5, 1, 1)).toBe("12,5");
    expect(formatNumber(30, 1, 1)).toBe("30,0");
  });
});
