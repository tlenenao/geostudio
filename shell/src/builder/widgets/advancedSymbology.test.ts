// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test } from "vitest";
import {
  BIVARIATE_COLORS,
  buildEffectLayers,
  generateDots,
  type AdvancedSymbology,
} from "./advancedSymbology";
import { buildLegend, buildMapPaint, paintExtrasOf, type LayerSymbology } from "./mapSymbology";

const square = (x: number, y: number, s: number) => ({
  type: "Polygon",
  coordinates: [
    [
      [x, y],
      [x + s, y],
      [x + s, y + s],
      [x, y + s],
      [x, y],
    ],
  ],
});

const paintOf = (adv: AdvancedSymbology, kind: "point" | "line" | "polygon" = "polygon") =>
  buildMapPaint(
    undefined,
    null,
    null,
    kind,
    undefined,
    paintExtrasOf({ advanced: adv }, undefined),
  );

describe("modes avancés — peinture", () => {
  test("predominant : case sur le champ maximal, une couleur par champ", () => {
    const { paint } = paintOf({ kind: "predominant", fields: ["a", "b", "c"] });
    const expr = paint["fill-color"] as unknown[];
    expect(expr[0]).toBe("case");
    // 3 branches (cond, couleur) + défaut
    expect(expr).toHaveLength(1 + 3 * 2 + 1);
  });

  test("bivarié : match sur y*3+x, 9 couleurs", () => {
    const { paint } = paintOf({
      kind: "bivariate",
      fieldX: "x",
      fieldY: "y",
      domainX: { min: 0, max: 30 },
      domainY: { min: 0, max: 90 },
      computedAt: "t",
    });
    const expr = paint["fill-color"] as unknown[];
    expect(expr[0]).toBe("match");
    expect(expr.slice(2).filter((v) => BIVARIATE_COLORS.includes(v as string))).toHaveLength(10);
  });

  test("bivarié dégénéré (min=max) : couleur constante, jamais d'expression cassée", () => {
    const { paint } = paintOf({
      kind: "bivariate",
      fieldX: "x",
      fieldY: "y",
      domainX: { min: 5, max: 5 },
      domainY: { min: 0, max: 9 },
      computedAt: "t",
    });
    expect(paint["fill-color"]).toBe(BIVARIATE_COLORS[0]);
  });

  test("compare : interpolation divergente centrée sur 0, sur une ligne aussi", () => {
    const { paint } = paintOf(
      { kind: "compare", fieldA: "a", fieldB: "b", maxAbs: 40, computedAt: "t" },
      "line",
    );
    const expr = paint["line-color"] as unknown[];
    expect(expr.slice(0, 2)).toEqual(["interpolate", ["linear"]]);
    expect(expr.filter((v) => typeof v === "number")).toEqual([-40, 0, 40]);
  });

  test("dotDensity : fond neutre + dots demandés pour un polygone, rien pour un point", () => {
    const adv: AdvancedSymbology = {
      kind: "dotDensity",
      field: "pop",
      valuePerDot: 100,
      color: "#123456",
    };
    const poly = paintOf(adv);
    expect(poly.dots).toEqual({ field: "pop", valuePerDot: 100, color: "#123456" });
    expect(poly.paint["fill-opacity"]).toBeLessThan(0.5);
    expect(paintOf(adv, "point").dots).toBeUndefined();
  });
});

describe("modes avancés — légende", () => {
  test.each([
    [{ kind: "predominant", fields: ["a", "b"] } as AdvancedSymbology, "predominant"],
    [
      {
        kind: "bivariate",
        fieldX: "x",
        fieldY: "y",
        domainX: { min: 0, max: 1 },
        domainY: { min: 0, max: 1 },
        computedAt: "t",
      } as AdvancedSymbology,
      "bivariate",
    ],
    [
      {
        kind: "compare",
        fieldA: "a",
        fieldB: "b",
        maxAbs: 3,
        computedAt: "t",
      } as AdvancedSymbology,
      "compare",
    ],
    [
      { kind: "dotDensity", field: "p", valuePerDot: 10, color: "#000000" } as AdvancedSymbology,
      "dotDensity",
    ],
  ])("%j", (adv, kind) => {
    const legend = buildLegend(
      undefined,
      null,
      null,
      "polygon",
      undefined,
      paintExtrasOf({ advanced: adv }, undefined),
    );
    expect(legend?.advanced?.kind).toBe(kind);
  });

  test("predominant à un seul champ : pas de légende", () => {
    const sym: LayerSymbology = { advanced: { kind: "predominant", fields: ["a"] } };
    expect(
      buildLegend(undefined, null, null, "polygon", undefined, paintExtrasOf(sym, undefined)),
    ).toBeNull();
  });
});

describe("effets", () => {
  test("polygone : ombre fill décalée, bloom/fusion en contour flou", () => {
    const fx = buildEffectLayers({ shadow: true, bloom: true, blend: true }, "fill", {
      "fill-color": "#ff0000",
    });
    expect(fx.map((f) => [f.suffix, f.type])).toEqual([
      ["__fx_shadow", "fill"],
      ["__fx_bloom", "line"],
      ["__fx_blend", "line"],
    ]);
    expect(fx[1].paint["line-color"]).toBe("#ff0000");
  });

  test("cercle : le rayon data-driven est conservé dans le halo", () => {
    const radius = ["interpolate", ["linear"], ["get", "n"], 0, 4, 9, 24];
    const [bloom] = buildEffectLayers({ bloom: true }, "circle", { "circle-radius": radius });
    expect(bloom.paint["circle-radius"]).toEqual(["*", 2, radius]);
    expect(bloom.paint["circle-blur"]).toBe(1);
  });

  test("aucun effet : aucune couche", () => {
    expect(buildEffectLayers(undefined, "fill", {})).toEqual([]);
    expect(buildEffectLayers({}, "fill", {})).toEqual([]);
  });
});

describe("generateDots", () => {
  const cfg = { field: "pop", valuePerDot: 10 };

  test("nombre de points = valeur / valuePerDot, tous dans le polygone", () => {
    const out = generateDots(
      [{ id: 1, properties: { pop: 200 }, geometry: square(0, 0, 10) }],
      cfg,
    );
    expect(out.features).toHaveLength(20);
    for (const f of out.features) {
      const [x, y] = f.geometry.coordinates;
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(10);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(10);
    }
  });

  test("déterministe (garde d'idempotence des idle)", () => {
    const pieces = [{ id: 1, properties: { pop: 100 }, geometry: square(0, 0, 10) }];
    expect(JSON.stringify(generateDots(pieces, cfg))).toBe(
      JSON.stringify(generateDots(pieces, cfg)),
    );
  });

  test("respecte les trous (anneau intérieur)", () => {
    const withHole = {
      type: "Polygon",
      coordinates: [
        ...square(0, 0, 10).coordinates,
        [
          [1, 1],
          [1, 9],
          [9, 9],
          [9, 1],
          [1, 1],
        ],
      ],
    };
    const out = generateDots([{ id: 1, properties: { pop: 300 }, geometry: withHole }], cfg);
    expect(out.features.length).toBeGreaterThan(0);
    for (const f of out.features) {
      const [x, y] = f.geometry.coordinates;
      expect(x < 1 || x > 9 || y < 1 || y > 9).toBe(true);
    }
  });

  test("morceaux de tuile d'une même entité : le total reste celui de l'entité", () => {
    const out = generateDots(
      [
        { id: 7, properties: { pop: 400 }, geometry: square(0, 0, 10) },
        { id: 7, properties: { pop: 400 }, geometry: square(10, 0, 10) },
      ],
      cfg,
    );
    expect(out.features.length).toBeGreaterThanOrEqual(39);
    expect(out.features.length).toBeLessThanOrEqual(41);
  });

  test("plafond, valeur invalide, valuePerDot nul", () => {
    const big = [{ id: 1, properties: { pop: 1e9 }, geometry: square(0, 0, 1) }];
    expect(generateDots(big, cfg, 50).features).toHaveLength(50);
    expect(
      generateDots([{ id: 1, properties: { pop: "x" }, geometry: square(0, 0, 1) }], cfg).features,
    ).toHaveLength(0);
    expect(generateDots(big, { field: "pop", valuePerDot: 0 }).features).toHaveLength(0);
  });
});
