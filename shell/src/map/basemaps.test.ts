// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { resolveBasemapStyle } from "./basemaps";

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
