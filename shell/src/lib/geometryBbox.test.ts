// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { bboxFromGeometry } from "./geometryBbox";

test("returns a degenerate bbox for a Point", () => {
  expect(bboxFromGeometry({ type: "Point", coordinates: [2.4, 46.6] })).toEqual([2.4, 46.6, 2.4, 46.6]);
});

test("returns the enclosing bbox for a Polygon", () => {
  const polygon = {
    type: "Polygon",
    coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]],
  };
  expect(bboxFromGeometry(polygon)).toEqual([2.0, 48.0, 3.0, 49.0]);
});

test("returns the enclosing bbox across a MultiPolygon's parts", () => {
  const multi = {
    type: "MultiPolygon",
    coordinates: [
      [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
      [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]],
    ],
  };
  expect(bboxFromGeometry(multi)).toEqual([0, 0, 11, 11]);
});

test("returns null for undefined, null, or a non-geometry value", () => {
  expect(bboxFromGeometry(undefined)).toBeNull();
  expect(bboxFromGeometry(null)).toBeNull();
  expect(bboxFromGeometry({ foo: "bar" })).toBeNull();
});
