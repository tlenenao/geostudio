// SPDX-License-Identifier: Apache-2.0
// Mesure géodésique maison (SP-27 §3) : haversine (sphère, rayon moyen
// terrestre) pour la distance, shoelace sphérique pour la surface. Aucune
// bibliothèque — précédent jenksBreaks/popupTemplate.
export type LngLat = { lng: number; lat: number };

export type SketchShape =
  | { kind: "freehand"; points: LngLat[]; color: string }
  | { kind: "rect"; from: LngLat; to: LngLat; color: string }
  | { kind: "circle"; center: LngLat; edge: LngLat; color: string }
  | { kind: "polygon"; points: LngLat[]; color: string }
  | { kind: "text"; at: LngLat; text: string; color: string };

const EARTH_RADIUS_M = 6_371_000;
const CIRCLE_STEPS = 32;
// Approximation d'un degré à l'équateur, utilisée UNIQUEMENT pour dessiner un
// cercle de croquis à l'écran : une annotation, pas une mesure. La distance
// exacte (haversine) sert seulement à le dimensionner depuis deux clics.
//
// LIMITE CONNUE ET ASSUMÉE (constat Mineur 7) : la même valeur est appliquée
// aux DEUX axes. À 48° N (cos ≈ 0,669) le rayon est-ouest est ~1,5× trop
// petit, et l'anneau tracé NE PASSE PAS par le point cliqué — il est
// visiblement ovale et plus étroit que le geste. Corriger demanderait de
// diviser le delta de longitude par cos(lat), au prix d'une singularité aux
// pôles. Non fait : croquis éphémère, jamais persisté, aucune valeur
// numérique affichée.
const METERS_PER_DEGREE_APPROX = 111_320;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

export function haversineDistanceMeters(a: LngLat, b: LngLat): number {
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function lineDistanceMeters(points: LngLat[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++)
    total += haversineDistanceMeters(points[i - 1], points[i]);
  return total;
}

// Shoelace sphérique : somme de (Δlng) × (2 + sin lat_i + sin lat_i+1), mise
// à l'échelle par R²/2. Exacte pour des polygones petits devant le rayon
// terrestre — tout cas d'usage réaliste de mesure sur carte ; pas prévue pour
// des surfaces à l'échelle continentale.
export function sphericalPolygonAreaSquareMeters(points: LngLat[]): number {
  const closed =
    points.length >= 2 &&
    points[0].lng === points[points.length - 1].lng &&
    points[0].lat === points[points.length - 1].lat;
  const ring = closed ? points.slice(0, -1) : points;
  if (ring.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const p1 = ring[i];
    const p2 = ring[(i + 1) % ring.length];
    sum += toRad(p2.lng - p1.lng) * (2 + Math.sin(toRad(p1.lat)) + Math.sin(toRad(p2.lat)));
  }
  return Math.abs((sum * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2);
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} km`;
}

export function formatArea(squareMeters: number): string {
  if (squareMeters < 10_000) return `${Math.round(squareMeters).toLocaleString("fr-FR")} m²`;
  if (squareMeters < 1_000_000)
    return `${(squareMeters / 10_000).toLocaleString("fr-FR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} ha`;
  return `${(squareMeters / 1_000_000).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} km²`;
}

export type SketchFeature = {
  type: "Feature";
  properties: { color: string; text?: string };
  geometry:
    | { type: "LineString"; coordinates: number[][] }
    | { type: "Polygon"; coordinates: number[][][] }
    | { type: "Point"; coordinates: number[] };
};

const xy = (p: LngLat): number[] => [p.lng, p.lat];

export function shapeToGeoJSONFeature(shape: SketchShape): SketchFeature {
  const properties: SketchFeature["properties"] =
    shape.kind === "text" ? { color: shape.color, text: shape.text } : { color: shape.color };
  if (shape.kind === "freehand") {
    return {
      type: "Feature",
      properties,
      geometry: { type: "LineString", coordinates: shape.points.map(xy) },
    };
  }
  if (shape.kind === "polygon") {
    // Garde explicite (constat Mineur 6) : sans elle, `points: []` lève sur
    // `xy(shape.points[0])` (lecture de `undefined.lng`). Aucun appelant de ce
    // plan ne peut y arriver — Task 17 n'offre « Terminer le polygone » qu'à
    // partir de 3 sommets, Task 18 ne rend un polygone en cours qu'à partir de
    // 2 points — mais c'est une fonction PURE et exportée : son contrat doit
    // tenir seul.
    if (shape.points.length === 0) {
      return { type: "Feature", properties, geometry: { type: "Polygon", coordinates: [[]] } };
    }
    const ring = [...shape.points.map(xy), xy(shape.points[0])];
    return { type: "Feature", properties, geometry: { type: "Polygon", coordinates: [ring] } };
  }
  if (shape.kind === "rect") {
    const { from, to } = shape;
    return {
      type: "Feature",
      properties,
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [from.lng, from.lat],
            [to.lng, from.lat],
            [to.lng, to.lat],
            [from.lng, to.lat],
            [from.lng, from.lat],
          ],
        ],
      },
    };
  }
  if (shape.kind === "circle") {
    const radiusDeg = haversineDistanceMeters(shape.center, shape.edge) / METERS_PER_DEGREE_APPROX;
    const ring = Array.from({ length: CIRCLE_STEPS + 1 }, (_, i) => {
      const t = (i / CIRCLE_STEPS) * 2 * Math.PI;
      return [
        shape.center.lng + radiusDeg * Math.cos(t),
        shape.center.lat + radiusDeg * Math.sin(t),
      ];
    });
    return { type: "Feature", properties, geometry: { type: "Polygon", coordinates: [ring] } };
  }
  return { type: "Feature", properties, geometry: { type: "Point", coordinates: xy(shape.at) } };
}
