// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { findOffendersInSource } from "./check-raw-colors.mjs";

describe("findOffendersInSource", () => {
  it("signale un hexadécimal littéral sans pragma", () => {
    expect(findOffendersInSource('const C = "#2563eb";', "a.ts")).toEqual([
      'a.ts:1: const C = "#2563eb";',
    ]);
  });

  it("accepte le pragma de ligne sur la ligne précédente", () => {
    const src = ["// gs-raw-color-ok: trait d'icône figé", 'const C = "#1e293b";'].join("\n");
    expect(findOffendersInSource(src, "a.ts")).toEqual([]);
  });

  it("une région begin/end couvre un bloc, la détection reprend après end", () => {
    const src = [
      "// gs-raw-color-ok-begin: palette de dataviz",
      'const A = ["#2563eb",',
      '  "#dc2626"];',
      "// gs-raw-color-ok-end",
      'const B = "#ffffff";',
    ].join("\n");
    expect(findOffendersInSource(src, "p.ts")).toEqual(['p.ts:5: const B = "#ffffff";']);
  });

  it("signale une région jamais fermée", () => {
    const src = ["// gs-raw-color-ok-begin: palette", 'const A = "#2563eb";'].join("\n");
    expect(findOffendersInSource(src, "p.ts")).toEqual([
      "p.ts:1: région gs-raw-color-ok-begin jamais fermée par gs-raw-color-ok-end",
    ]);
  });

  it("signale toujours une classe Tailwind de couleur littérale", () => {
    expect(findOffendersInSource('<p className="text-white" />', "b.tsx")).toEqual([
      'b.tsx:1: <p className="text-white" />',
    ]);
  });
});
