// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { formatBytes, formatDateTime, formatNumber } from "./format";

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

describe("formatBytes (P26.07)", () => {
  it("adapte l'unité et utilise la virgule fr", () => {
    expect(formatBytes(512)).toBe("512 o");
    expect(formatBytes(3 * 1024)).toBe("3 Ko");
    expect(formatBytes(1.5 * 1024 * 1024)).toMatch(/^1,5 Mo$/);
    expect(formatBytes(2 * 1024 ** 3)).toBe("2 Go");
  });
});

describe("valeur absente ou non finie (REV-285 g)", () => {
  it("formatNumber rend « — » pour NaN, ±Infinity, null et undefined", () => {
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe("—");
    expect(formatNumber(Number.NEGATIVE_INFINITY)).toBe("—");
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(0)).toBe("0");
  });

  it("formatBytes rend « — » pour une taille non finie", () => {
    expect(formatBytes(Number.NaN)).toBe("—");
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(0)).toBe("0 o");
  });

  it("formatDateTime rend « — » pour null, undefined et la chaîne vide (pas 1970)", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });
});
