// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, test } from "vitest";
import {
  BASEMAPS,
  BLANK_BASEMAP,
  DEFAULT_BASEMAP,
  allowedBasemaps,
  defaultBasemapStyle,
  resolveBasemapStyle,
} from "./basemaps";

describe("fonds de carte souverains (AUD-122)", () => {
  it("propose les fonds IGN Géoplateforme en raster", () => {
    const ign = BASEMAPS.filter((b) => b.id.startsWith("ign-"));
    expect(ign.map((b) => b.id)).toEqual(["ign-plan", "ign-ortho"]);
    for (const b of ign) expect(b.style.startsWith("xyz:https://data.geopf.fr/wmts?")).toBe(true);
    const style = resolveBasemapStyle(ign[0].style);
    expect(typeof style).toBe("object");
    if (typeof style === "object") {
      const source = style.sources.basemap as { attribution?: string };
      expect(source.attribution).toContain("IGN");
    }
  });

  it("masque les fonds externes et passe au fond vierge en mode souverain", () => {
    expect(defaultBasemapStyle(true)).toBe(DEFAULT_BASEMAP.style);
    expect(defaultBasemapStyle(false)).toBe("/basemaps/blank.json");
    expect(allowedBasemaps(BASEMAPS, false)).toEqual([BLANK_BASEMAP]);
    expect(allowedBasemaps(BASEMAPS, true)).toEqual(BASEMAPS);
  });
});

test("une URL de style est transmise telle quelle", () => {
  expect(resolveBasemapStyle("https://h/style.json")).toBe("https://h/style.json");
});

test("un fond xyz: devient un style raster minimal", () => {
  const style = resolveBasemapStyle("xyz:https://h/{z}/{x}/{y}.png");
  expect(style).toMatchObject({
    version: 8,
    sources: { basemap: { type: "raster", tiles: ["https://h/{z}/{x}/{y}.png"] } },
    layers: [{ type: "raster", source: "basemap" }],
  });
});
