// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import type { MapLayer } from "../api/types";
import type { LayerSymbology } from "../builder/widgets/mapSymbology";
import { effectivePaint } from "./mapLayerBuild";
import { exportMapLibreStyle, importMapLibreStyle } from "./mapLibreStyle";

const symbology: LayerSymbology = {
  color: {
    field: "type",
    mode: "categorical",
    palette: "categorical-b",
    domain: { kind: "categorical", values: ["a", "b"] },
    computedAt: "2026-01-01",
  },
  stroke: { color: { fixed: "#112233" }, width: { fixed: 2 }, style: "dashed" },
  opacity: 40,
};
const layers: MapLayer[] = [
  {
    id: "communes",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "/v1/collections/communes/tiles/{z}/{x}/{y}.mvt",
    sourceLayer: "communes",
    geometryKind: "polygon",
    symbology,
  },
  {
    id: "pts",
    title: "Points",
    visible: false,
    kind: "feature",
    url: "https://exemple.test/p.geojson",
    renderAs: "circle",
    paint: { "circle-color": "#ff0000" },
  },
  {
    id: "ortho",
    title: "Ortho",
    visible: true,
    kind: "raster",
    tilesUrl: "https://t/{z}/{x}/{y}.png",
    opacity: 0.5,
  },
  { id: "d", title: "Deck", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "/x" },
];

describe("style MapLibre (ARC-28)", () => {
  it("rechargé = même paint (par couche), outline comprise, deck ignoré", () => {
    const style = exportMapLibreStyle(layers, "Ma carte");
    expect(style.version).toBe(8);
    expect(style.layers.map((l) => l.id)).toEqual([
      "communes",
      "communes__outline",
      "pts",
      "ortho",
    ]);
    const back = importMapLibreStyle(JSON.parse(JSON.stringify(style)));
    expect(back.skipped).toEqual([]);
    expect(back.layers.map((l) => l.id)).toEqual(["communes", "pts", "ortho"]);
    const [c0, c1] = [layers[0], back.layers[0]];
    if (c0.kind !== "vector" || c1.kind !== "vector") throw new Error("kind");
    expect(effectivePaint(c1, "polygon", undefined)).toEqual(
      effectivePaint(c0, "polygon", undefined),
    );
    expect(c1.symbology).toEqual(symbology);
    expect(back.layers[1]).toMatchObject({
      kind: "feature",
      visible: false,
      renderAs: "circle",
      paint: { "circle-color": "#ff0000" },
    });
    expect(back.layers[2]).toMatchObject({ kind: "raster", opacity: 0.5 });
  });

  it("le paint exporté est celui du rendu (couleur data-driven + opacité)", () => {
    const style = exportMapLibreStyle(layers, "x");
    const paint = style.layers[0].paint as Record<string, unknown>;
    expect(paint["fill-color"]).toEqual(expect.arrayContaining(["match"]));
    expect(paint["fill-opacity"]).toBe(0.4);
  });

  it("style étranger : repris via paint, valeurs hostiles écartées", () => {
    const foreign = {
      version: 8,
      sources: {
        v: { type: "vector", tiles: ["https://t/{z}/{x}/{y}.pbf"] },
        bad: { type: "geojson", data: "javascript:alert(1)" },
        d: { type: "geojson", data: "data:text/plain,x" },
      },
      layers: [
        { id: "bg", type: "background", paint: {} },
        {
          id: "roads",
          type: "line",
          source: "v",
          "source-layer": "roads",
          paint: { "line-color": "#abcdef" },
        },
        { id: "x", type: "fill", source: "bad", paint: {} },
        { id: "y", type: "fill", source: "d", paint: {} },
        { id: "z", type: "fill", source: "v" },
        { id: "roads", type: "line", source: "v", "source-layer": "r" },
        42,
      ],
    };
    const r = importMapLibreStyle(foreign);
    expect(r.layers).toHaveLength(1);
    expect(r.layers[0]).toMatchObject({
      kind: "vector",
      sourceLayer: "roads",
      paint: { "line-color": "#abcdef" },
    });
    expect([...r.skipped].sort()).toEqual(["bg", "roads", "x", "y", "z"]);
  });

  it("ne lève jamais sur une entrée invalide", () => {
    for (const bad of [null, 3, "x", {}, { version: 7 }, { version: 8, layers: "a" }])
      expect(importMapLibreStyle(bad)).toEqual({ layers: [], skipped: [] });
  });
});
