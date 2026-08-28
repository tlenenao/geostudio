// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import {
  formatArea,
  formatDistance,
  haversineDistanceMeters,
  lineDistanceMeters,
  shapeToGeoJSONFeature,
  sphericalPolygonAreaSquareMeters,
} from "./measureSketch";

test("haversineDistanceMeters : 1° de longitude à l'équateur vaut ~111,2 km", () => {
  const d = haversineDistanceMeters({ lng: 0, lat: 0 }, { lng: 1, lat: 0 });
  expect(d).toBeGreaterThan(111_000);
  expect(d).toBeLessThan(111_500);
});

test("haversineDistanceMeters : deux fois le même point vaut 0", () => {
  expect(haversineDistanceMeters({ lng: 2, lat: 45 }, { lng: 2, lat: 45 })).toBe(0);
});

test("lineDistanceMeters somme les segments consécutifs", () => {
  const pts = [
    { lng: 0, lat: 0 },
    { lng: 1, lat: 0 },
    { lng: 1, lat: 1 },
  ];
  const expected =
    haversineDistanceMeters(pts[0], pts[1]) + haversineDistanceMeters(pts[1], pts[2]);
  expect(lineDistanceMeters(pts)).toBeCloseTo(expected, 0);
});

test("lineDistanceMeters vaut 0 sous 2 points", () => {
  expect(lineDistanceMeters([])).toBe(0);
  expect(lineDistanceMeters([{ lng: 0, lat: 0 }])).toBe(0);
});

test("sphericalPolygonAreaSquareMeters : un petit carré équatorial colle à l'estimation plane à 1 %", () => {
  const ring = [
    { lng: 0, lat: 0 },
    { lng: 0.01, lat: 0 },
    { lng: 0.01, lat: 0.01 },
    { lng: 0, lat: 0.01 },
    { lng: 0, lat: 0 },
  ];
  const area = sphericalPolygonAreaSquareMeters(ring);
  const side = haversineDistanceMeters({ lng: 0, lat: 0 }, { lng: 0.01, lat: 0 });
  const flat = side * side;
  expect(Math.abs(area - flat) / flat).toBeLessThan(0.01);
});

test("sphericalPolygonAreaSquareMeters vaut 0 sous 3 points distincts", () => {
  expect(
    sphericalPolygonAreaSquareMeters([
      { lng: 0, lat: 0 },
      { lng: 1, lat: 0 },
    ]),
  ).toBe(0);
});

test("formatDistance passe des mètres aux kilomètres à 1000 m", () => {
  expect(formatDistance(500)).toBe("500 m");
  expect(formatDistance(1500)).toBe("1,50 km");
});

// toLocaleString("fr-FR") sépare les milliers par U+202F (NARROW NO-BREAK
// SPACE), PAS par une espace ASCII. Écrit en ÉCHAPPEMENT `\u202f` — et non en
// caractère littéral, comme le faisait la version précédente de ce test
// (constat Mineur 5) — pour que le caractère soit visible en revue et
// insensible à une normalisation d'espace par un copier-coller.
test("formatArea passe de m² à ha puis à km²", () => {
  expect(formatArea(5000)).toBe("5\u202f000 m²");
  expect(formatArea(50_000)).toBe("5,00 ha");
  expect(formatArea(5_000_000)).toBe("5,00 km²");
});

test("shapeToGeoJSONFeature produit la géométrie attendue par type de forme", () => {
  const color = "#dc2626";
  expect(
    shapeToGeoJSONFeature({
      kind: "rect",
      from: { lng: 0, lat: 0 },
      to: { lng: 2, lat: 1 },
      color,
    }).geometry,
  ).toEqual({
    type: "Polygon",
    coordinates: [
      [
        [0, 0],
        [2, 0],
        [2, 1],
        [0, 1],
        [0, 0],
      ],
    ],
  });

  const freehand = shapeToGeoJSONFeature({
    kind: "freehand",
    points: [
      { lng: 0, lat: 0 },
      { lng: 1, lat: 1 },
    ],
    color,
  });
  expect(freehand.geometry).toEqual({
    type: "LineString",
    coordinates: [
      [0, 0],
      [1, 1],
    ],
  });
  expect(freehand.properties).toEqual({ color });

  const circle = shapeToGeoJSONFeature({
    kind: "circle",
    center: { lng: 0, lat: 0 },
    edge: { lng: 0.1, lat: 0 },
    color,
  });
  expect(circle.geometry.type).toBe("Polygon");
  // 32 segments + le point de fermeture.
  expect((circle.geometry as { coordinates: number[][][] }).coordinates[0]).toHaveLength(33);

  const text = shapeToGeoJSONFeature({
    kind: "text",
    at: { lng: 3, lat: 4 },
    text: "Rendez-vous",
    color,
  });
  expect(text.geometry).toEqual({ type: "Point", coordinates: [3, 4] });
  expect(text.properties).toEqual({ color, text: "Rendez-vous" });
});
