import { expect, test } from "vitest";
import { tileKeys } from "./viewportTiles";

test("une vue serrée donne les tuiles du zoom entier courant", () => {
  const keys = tileKeys({ zoom: 12.7, bounds: [2.34, 48.85, 2.36, 48.86] });
  expect(keys.length).toBeGreaterThan(0);
  expect(keys.every((k) => k.startsWith("12/"))).toBe(true);
});

test("une vue large à zoom élevé est rabaissée à 12 tuiles au plus", () => {
  const keys = tileKeys({ zoom: 14, bounds: [-5, 41, 9, 51] });
  expect(keys.length).toBeLessThanOrEqual(12);
  expect(Number(keys[0].split("/")[0])).toBeLessThan(14);
});

test("le monde entier à z0 est la tuile 0/0/0", () => {
  expect(tileKeys({ zoom: 0, bounds: [-180, -85, 180, 85] })).toEqual(["0/0/0"]);
});
