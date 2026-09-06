// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { DEFAULT_BASEMAP } from "../map/basemaps";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";

export type Bbox = [number, number, number, number]; // [minLon, minLat, maxLon, maxLat]

const RECT_SOURCE_ID = "catalog-spatial-filter-rect";
const RECT_LAYER_ID = "catalog-spatial-filter-rect-fill";
const RECT_OUTLINE_LAYER_ID = "catalog-spatial-filter-rect-outline";

function toBbox(a: { lng: number; lat: number }, b: { lng: number; lat: number }): Bbox {
  return [
    Math.min(a.lng, b.lng),
    Math.min(a.lat, b.lat),
    Math.max(a.lng, b.lng),
    Math.max(a.lat, b.lat),
  ];
}

function bboxToGeoJSON(bbox: Bbox) {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  return {
    type: "Feature" as const,
    properties: {},
    geometry: {
      type: "Polygon" as const,
      coordinates: [
        [
          [minLon, minLat],
          [maxLon, minLat],
          [maxLon, maxLat],
          [minLon, maxLat],
          [minLon, minLat],
        ],
      ],
    },
  };
}

const EMPTY_FEATURE_COLLECTION = { type: "FeatureCollection" as const, features: [] };

/** Carte MapLibre autonome (pas de dépendance à measureSketch.ts — logique
 * de rectangle bien plus simple qu'un polygone libre, spec SP-55 §2.6) :
 * clic-glisser-relâcher dessine un rectangle, remonté au parent comme
 * `[minLon, minLat, maxLon, maxLat]` pour peupler `ListItemsParams.bbox`. */
export function CatalogSpatialFilter({ onChange }: { onChange: (bbox: Bbox | null) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const startRef = useRef<{ lng: number; lat: number } | null>(null);
  const draggingRef = useRef(false);
  const [bbox, setBbox] = useState<Bbox | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DEFAULT_BASEMAP.style,
      center: [2.35, 46.6],
      zoom: 4,
      // Contrôle d'attribution désactivé (audit a11y SP-57a) : ce mini-fond
      // de carte est un widget de sélection décoratif (`role="img"` sur son
      // conteneur, cf. plus bas) — le contrôle par défaut de MapLibre y
      // insère un `<summary>`/`<a>` interactifs et focusables, ce que
      // axe-core signale à juste titre (`nested-interactive`, serious) :
      // du contenu interactif ne doit jamais être imbriqué dans un élément
      // dont le rôle ARIA implique l'absence d'interaction. L'attribution
      // réelle reste portée par la carte principale de l'éditeur.
      attributionControl: false,
      // dragPan désactivé : un simple clic-glisser doit dessiner le
      // rectangle (mousedown/mousemove/mouseup ci-dessous), pas déplacer la
      // vue sous le curseur pendant le geste — les deux gestionnaires
      // recevraient sinon le même événement, et la position lngLat au
      // relâchement refléterait un fond de carte qui a bougé pendant le
      // tracé, faussant le rectangle perçu par l'utilisateur.
      dragPan: false,
      boxZoom: false,
    });
    mapRef.current = map;

    function ensureRectLayer() {
      if (!map.getSource(RECT_SOURCE_ID)) {
        map.addSource(RECT_SOURCE_ID, { type: "geojson", data: EMPTY_FEATURE_COLLECTION });
        map.addLayer({
          id: RECT_LAYER_ID,
          type: "fill",
          source: RECT_SOURCE_ID,
          paint: { "fill-color": "#3388ff", "fill-opacity": 0.2 },
        });
        map.addLayer({
          id: RECT_OUTLINE_LAYER_ID,
          type: "line",
          source: RECT_SOURCE_ID,
          paint: { "line-color": "#3388ff", "line-width": 2 },
        });
      }
    }

    function setRectData(next: Bbox | null) {
      const source = map.getSource(RECT_SOURCE_ID) as
        { setData?: (d: unknown) => void } | undefined;
      source?.setData?.(
        next
          ? { type: "FeatureCollection", features: [bboxToGeoJSON(next)] }
          : EMPTY_FEATURE_COLLECTION,
      );
    }

    function onMouseDown(e: { lngLat: { lng: number; lat: number } }) {
      startRef.current = e.lngLat;
      draggingRef.current = true;
    }
    function onMouseMove(e: { lngLat: { lng: number; lat: number } }) {
      if (!draggingRef.current || !startRef.current) return;
      setRectData(toBbox(startRef.current, e.lngLat));
    }
    function onMouseUp(e: { lngLat: { lng: number; lat: number } }) {
      if (!draggingRef.current || !startRef.current) return;
      const result = toBbox(startRef.current, e.lngLat);
      draggingRef.current = false;
      startRef.current = null;
      setBbox(result);
      onChange(result);
    }

    map.on("load", ensureRectLayer);
    map.on("mousedown", onMouseDown as never);
    map.on("mousemove", onMouseMove as never);
    map.on("mouseup", onMouseUp as never);

    return () => {
      map.off("load", ensureRectLayer);
      map.off("mousedown", onMouseDown as never);
      map.off("mousemove", onMouseMove as never);
      map.off("mouseup", onMouseUp as never);
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onChange stable côté appelant (setState), pas de dépendance réelle
  }, []);

  function clear() {
    setBbox(null);
    onChange(null);
    const source = mapRef.current?.getSource(RECT_SOURCE_ID) as
      { setData?: (d: unknown) => void } | undefined;
    source?.setData?.(EMPTY_FEATURE_COLLECTION);
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        ref={containerRef}
        role="img"
        aria-label={t("catalog.spatialDrawAria")}
        className="h-48 w-full rounded-md border border-rule"
      />
      <Button type="button" variant="outline" size="sm" onClick={clear} disabled={!bbox}>
        {t("common.clear")}
      </Button>
    </div>
  );
}
