// SPDX-License-Identifier: Apache-2.0
// Recursively walks GeoJSON coordinate arrays (any depth: Point, LineString,
// Polygon, Multi*) to compute an enclosing [minX, minY, maxX, maxY] — no
// turf/geojson dependency, neither is present in this repo (DataRecord.geometry
// is typed `unknown` for the same reason, api/types.ts:351).
function walk(coords: unknown, acc: [number, number, number, number]): void {
  if (Array.isArray(coords) && typeof coords[0] === "number") {
    const [x, y] = coords as [number, number];
    if (x < acc[0]) acc[0] = x;
    if (y < acc[1]) acc[1] = y;
    if (x > acc[2]) acc[2] = x;
    if (y > acc[3]) acc[3] = y;
    return;
  }
  if (Array.isArray(coords)) coords.forEach((c) => walk(c, acc));
}

export function bboxFromGeometry(geometry: unknown): [number, number, number, number] | null {
  if (!geometry || typeof geometry !== "object" || !("coordinates" in geometry)) return null;
  const coords = (geometry as { coordinates: unknown }).coordinates;
  const acc: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  walk(coords, acc);
  if (!isFinite(acc[0])) return null;
  return acc;
}
