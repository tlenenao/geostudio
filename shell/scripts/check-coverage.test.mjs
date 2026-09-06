// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { checkCoverage, parseThresholds } from "./check-coverage.mjs";

function summary({ lines, branches, functions, statements }) {
  return {
    total: {
      lines: { pct: lines },
      branches: { pct: branches },
      functions: { pct: functions },
      statements: { pct: statements },
    },
  };
}

describe("parseThresholds", () => {
  it("un nombre nu (format historique) s'applique aux quatre métriques", () => {
    expect(parseThresholds("88")).toEqual({
      lines: 88,
      branches: 88,
      functions: 88,
      statements: 88,
    });
  });

  it("un objet JSON donne un seuil distinct par métrique", () => {
    expect(
      parseThresholds('{"lines": 90, "branches": 83, "functions": 88, "statements": 90}'),
    ).toEqual({
      lines: 90,
      branches: 83,
      functions: 88,
      statements: 90,
    });
  });
});

describe("checkCoverage", () => {
  const thresholds = { lines: 88, branches: 83, functions: 88, statements: 88 };

  it("ne signale rien quand les quatre métriques sont au-dessus du seuil", () => {
    const s = summary({ lines: 90, branches: 85, functions: 90, statements: 90 });
    expect(checkCoverage(s, thresholds)).toEqual([]);
  });

  it("signale lines seule si les trois autres passent — REV-078 : la porte d'origine ne lisait que lines.pct", () => {
    const s = summary({ lines: 80, branches: 85, functions: 90, statements: 90 });
    const failures = checkCoverage(s, thresholds);
    expect(failures).toHaveLength(1);
    expect(failures[0]).toMatchObject({ metric: "lines" });
  });

  it("signale branches seule quand lines/functions/statements passent — la régression que la porte d'origine laissait totalement passer", () => {
    const s = summary({ lines: 90, branches: 70, functions: 90, statements: 90 });
    const failures = checkCoverage(s, thresholds);
    expect(failures).toEqual([{ metric: "branches", measured: 70, threshold: 83 }]);
  });

  it("signale functions seule", () => {
    const s = summary({ lines: 90, branches: 85, functions: 50, statements: 90 });
    const failures = checkCoverage(s, thresholds);
    expect(failures.map((f) => f.metric)).toEqual(["functions"]);
  });

  it("signale statements seule", () => {
    const s = summary({ lines: 90, branches: 85, functions: 90, statements: 50 });
    const failures = checkCoverage(s, thresholds);
    expect(failures.map((f) => f.metric)).toEqual(["statements"]);
  });

  it("signale les quatre métriques quand toutes sont sous le seuil", () => {
    const s = summary({ lines: 10, branches: 10, functions: 10, statements: 10 });
    expect(checkCoverage(s, thresholds).map((f) => f.metric)).toEqual([
      "lines",
      "branches",
      "functions",
      "statements",
    ]);
  });
});
