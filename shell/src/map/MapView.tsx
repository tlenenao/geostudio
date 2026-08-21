// SPDX-License-Identifier: Apache-2.0
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer } from "@deck.gl/layers";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { Tiles3DLoader } from "@loaders.gl/3d-tiles";
import type { DataRecord, MapConfig } from "../api/types";
import { MapLegend } from "./MapLegend";

const HIGHLIGHT_ID = "__highlight__";
const TERRAIN_SOURCE_ID = "__terrain__";
// Path segments distinguishing our own authenticated proxies (served by
// core, design docs §4) from an externally-hosted resource at the same-
// looking path — the latter must never receive our session's bearer token.
const HOSTED_TILESET3D_PATH = "/tileset3d/";
const HOSTED_TERRAIN3D_PATH = "/terrain3d/";

// Real "is this hosted by us" check: a substring match on the URL is not
// enough — layer/terrain URLs are freeform (an author can type any external
// URL via LayerPicker/TerrainPanel), so an attacker-controlled URL like
// "https://attacker.example/x/terrain3d/y/tiles/0/0/0.png" would otherwise
// pass a bare `.includes(pathPrefix)` check and leak the session's bearer
// token cross-origin. A URL only counts as hosted when its origin matches
// the configured core API's origin AND its pathname starts with the proxy
// route's own path segment. Shared by both the tileset3d (deck.gl
// Tile3DLayer, see buildTiles3DLayer) and terrain3d (MapLibre
// transformRequest, see below) call sites — never duplicate this check.
function isHostedCoreUrl(url: string, coreUrl: string | undefined, pathPrefix: string): boolean {
  if (!coreUrl) return false;
  try {
    const target = new URL(url);
    const core = new URL(coreUrl);
    return target.origin === core.origin && target.pathname.startsWith(pathPrefix);
  } catch {
    return false;
  }
}

function isHostedTilesetUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TILESET3D_PATH);
}

function isHostedTerrainUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TERRAIN3D_PATH);
}

export type MapViewHandle = {
  flyTo: (opts: {
    center: [number, number];
    zoom?: number;
    pitch?: number;
    bearing?: number;
  }) => void;
  highlight: (geometry: unknown | null) => void;
};

function applyLayers(
  map: maplibregl.Map,
  layers: MapConfig["layers"],
  applied: Set<string>,
  clickHandlers: Map<string, (e: maplibregl.MapLayerMouseEvent) => void>,
  onFeatureClick: (record: DataRecord) => void,
) {
  applied.forEach((id) => {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
    const prevHandler = clickHandlers.get(id);
    if (prevHandler) {
      map.off("click", id, prevHandler);
      clickHandlers.delete(id);
    }
  });
  applied.clear();

  for (const layer of layers) {
    if (!layer.visible || layer.kind === "deck" || layer.kind === "tiles3d") continue;
    try {
      if (layer.kind === "vector") {
        map.addSource(layer.id, { type: "vector", tiles: [layer.tilesUrl] });
        map.addLayer({
          id: layer.id,
          type: "fill",
          source: layer.id,
          "source-layer": layer.sourceLayer,
          paint: layer.paint ?? {},
        });
      } else if (layer.kind === "raster") {
        map.addSource(layer.id, { type: "raster", tiles: [layer.tilesUrl], tileSize: 256 });
        map.addLayer({
          id: layer.id,
          type: "raster",
          source: layer.id,
          paint: { "raster-opacity": layer.opacity ?? 1 },
        });
      } else if (layer.kind === "feature") {
        map.addSource(layer.id, { type: "geojson", data: layer.url });
        switch (layer.renderAs ?? "fill") {
          case "circle":
            map.addLayer({
              id: layer.id,
              type: "circle",
              source: layer.id,
              paint: layer.paint ?? {},
            });
            break;
          case "line":
            map.addLayer({
              id: layer.id,
              type: "line",
              source: layer.id,
              paint: layer.paint ?? {},
            });
            break;
          default:
            map.addLayer({
              id: layer.id,
              type: "fill",
              source: layer.id,
              paint: layer.paint ?? {},
            });
            break;
        }
        const handler = (e: maplibregl.MapLayerMouseEvent) => {
          const f = e.features?.[0];
          if (!f || f.id == null) return;
          onFeatureClick({
            id: f.id as string | number,
            properties: f.properties ?? {},
            geometry: f.geometry,
          });
        };
        map.on("click", layer.id, handler);
        clickHandlers.set(layer.id, handler);
      }
      applied.add(layer.id);
    } catch (err) {
      // Per spec §8: one bad layer must not break the whole map. Roll back any
      // half-added source/layer so it can't orphan or clash on the next apply.
      if (map.getLayer(layer.id)) map.removeLayer(layer.id);
      if (map.getSource(layer.id)) map.removeSource(layer.id);
      console.error(`MapView: skipping layer ${layer.id}`, err);
    }
  }
}

type DeckLayer = Extract<MapConfig["layers"][number], { kind: "deck" }>;
type Tiles3DMapLayer = Extract<MapConfig["layers"][number], { kind: "tiles3d" }>;

function buildDeckLayer(layer: DeckLayer) {
  // Canonical fields last so user props can't shadow the id Deck.gl uses for
  // layer reconciliation, nor the data source.
  const props = { ...(layer.props ?? {}), id: layer.id, data: layer.dataUrl };
  switch (layer.deckType) {
    case "heatmap":
      return new HeatmapLayer(props);
    case "hexbin":
      return new HexagonLayer(props);
    case "column":
      return new ColumnLayer(props);
    default:
      // Exhaustiveness guard: a new deckType turns into a compile error here.
      return layer.deckType satisfies never;
  }
}

// Identity of a *tileset*, not of a layer: re-pointing the same layer id at a
// different tileset URL must invalidate the "already loaded" bookkeeping used
// by the export-readiness gate below.
function tilesetKey(layer: Tiles3DMapLayer) {
  return `${layer.id}\n${layer.url}`;
}

function buildTiles3DLayer(
  layer: Tiles3DMapLayer,
  onTilesetLoad?: (key: string) => void,
  getAuthToken?: () => string | undefined,
  getCoreUrl?: () => string,
) {
  const token = isHostedTilesetUrl(layer.url, getCoreUrl?.()) ? getAuthToken?.() : undefined;
  return new Tile3DLayer({
    id: layer.id,
    data: layer.url,
    loader: Tiles3DLoader,
    loadOptions: token ? { fetch: { headers: { Authorization: `Bearer ${token}` } } } : undefined,
    // Fired once the root tileset has loaded. Deck.gl loads 3D Tiles entirely
    // outside MapLibre's knowledge, so this is the only signal that tells the
    // export worker the tileset is actually on screen (see onReady below).
    onTilesetLoad: () => onTilesetLoad?.(tilesetKey(layer)),
  });
}

function applyDeckLayers(
  overlay: MapboxOverlay,
  layers: MapConfig["layers"],
  onTilesetLoad?: (key: string) => void,
  getAuthToken?: () => string | undefined,
  getCoreUrl?: () => string,
) {
  const deckLayers = layers
    .filter((l): l is DeckLayer => l.visible && l.kind === "deck")
    .map(buildDeckLayer);
  const tiles3dLayers = layers
    .filter((l): l is Tiles3DMapLayer => l.visible && l.kind === "tiles3d")
    .map((l) => buildTiles3DLayer(l, onTilesetLoad, getAuthToken, getCoreUrl));
  overlay.setProps({ layers: [...deckLayers, ...tiles3dLayers] });
}

// Full teardown-then-rebuild on every apply, mirroring applyLayers' pattern
// for the MapLibre-native layer array — simpler than diffing, and the only
// way to pick up a changed tilesUrl (MapLibre raster-dem sources are
// immutable once created).
function applyTerrain(map: maplibregl.Map, terrain: MapConfig["terrain"] | null | undefined) {
  map.setTerrain(null);
  if (map.getSource(TERRAIN_SOURCE_ID)) map.removeSource(TERRAIN_SOURCE_ID);
  // A blank URL is the transient state right after the author ticks "Activer
  // le terrain 3D" (TerrainPanel emits tilesUrl: "" first). Building a
  // raster-dem source on it fires doomed tile requests for nothing.
  if (!terrain || !terrain.tilesUrl.trim()) return;
  map.addSource(TERRAIN_SOURCE_ID, {
    type: "raster-dem",
    tiles: [terrain.tilesUrl],
    tileSize: 256,
    encoding: terrain.encoding,
  });
  map.setTerrain({ source: TERRAIN_SOURCE_ID, exaggeration: terrain.exaggeration ?? 1 });
}

export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: {
      center: [number, number];
      zoom: number;
      bbox: [number, number, number, number];
      pitch: number;
      bearing: number;
    }) => void;
    onFeatureClick?: (record: DataRecord) => void;
    // Fired once the map has settled after its first load (MapLibre "idle":
    // no pending tiles/style/sprite loads) *and* every visible tiles3d layer's
    // root tileset has loaded — the real "ready to capture" signal for
    // exportRender mode (SP-17a Task 10), as opposed to a fixed delay.
    // MapLibre knows nothing about deck.gl's Tile3DLayer streaming, so "idle"
    // on its own would let a capture happen with the tileset still missing.
    onReady?: () => void;
    // Suppresses the built-in interactive legend. Used by exportRender mode
    // (MapEditorPage), which renders its own legend overlay driven by
    // `printLayout.showLegend` — without this, that toggle couldn't ever
    // hide the legend from a capture (this MapLegend would still render
    // underneath it, and both would duplicate when showLegend is true).
    hideLegend?: boolean;
    // Authenticates Tile3DLayer requests against a hosted (design
    // /tileset3d/) tileset's proxy route — never sent for external tileset
    // URLs (see HOSTED_TILESET3D_PATH check in buildTiles3DLayer). Absent by
    // default: a MapView with no hosted tiles3d layer needs no auth plumbing.
    getAuthToken?: () => string | undefined;
    // The core API's base URL, used alongside getAuthToken to verify a
    // tiles3d layer's URL actually belongs to our own authenticated proxy
    // (origin+path check) before attaching a bearer token — see
    // isHostedTilesetUrl. Absent by default, same as getAuthToken.
    getCoreUrl?: () => string;
  }
>(function MapView(
  { config, onViewChange, onFeatureClick, onReady, hideLegend, getAuthToken, getCoreUrl },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const clickHandlersRef = useRef<Map<string, (e: maplibregl.MapLayerMouseEvent) => void>>(
    new Map(),
  );
  // The style's *initial* load — the only real precondition of addSource /
  // addLayer / setTerrain. `map.isStyleLoaded()` was used here before and is a
  // different question ("is nothing loading right now?"): a single in-flight
  // tile request made it return false, and every config update that landed in
  // that window was silently dropped with nothing to retry it.
  const styleLoadedRef = useRef(false);
  // Export readiness (onReady) = MapLibre idle AND every visible tiles3d
  // tileset loaded. Deck.gl's Tile3DLayer streams outside MapLibre, so "idle"
  // alone can fire while a tileset is still missing from the capture.
  const idleRef = useRef(false);
  const readyFiredRef = useRef(false);
  const loadedTilesetsRef = useRef<Set<string>>(new Set());
  // Keep the latest callback/layers reachable from the mount-time closures so
  // the async "load" and "moveend" handlers never read stale values.
  const onViewChangeRef = useRef(onViewChange);
  const onFeatureClickRef = useRef(onFeatureClick);
  const onReadyRef = useRef(onReady);
  const getAuthTokenRef = useRef(getAuthToken);
  const getCoreUrlRef = useRef(getCoreUrl);
  const layersRef = useRef(config.layers);
  const terrainRef = useRef(config.terrain);
  useEffect(() => {
    onViewChangeRef.current = onViewChange;
  }, [onViewChange]);
  useEffect(() => {
    onFeatureClickRef.current = onFeatureClick;
  }, [onFeatureClick]);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);
  useEffect(() => {
    getAuthTokenRef.current = getAuthToken;
  }, [getAuthToken]);
  useEffect(() => {
    getCoreUrlRef.current = getCoreUrl;
  }, [getCoreUrl]);
  useEffect(() => {
    layersRef.current = config.layers;
  });
  useEffect(() => {
    terrainRef.current = config.terrain;
  });

  const maybeFireReady = useCallback(() => {
    if (readyFiredRef.current || !idleRef.current) return;
    const pending = layersRef.current.some(
      (l) => l.visible && l.kind === "tiles3d" && !loadedTilesetsRef.current.has(tilesetKey(l)),
    );
    if (pending) return;
    readyFiredRef.current = true;
    onReadyRef.current?.();
  }, []);

  const handleTilesetLoad = useCallback(
    (key: string) => {
      loadedTilesetsRef.current.add(key);
      maybeFireReady();
    },
    [maybeFireReady],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
      pitch: config.view.pitch ?? 0,
      bearing: config.view.bearing ?? 0,
      transformRequest: (url: string) => {
        if (isHostedTerrainUrl(url, getCoreUrlRef.current?.())) {
          const token = getAuthTokenRef.current?.();
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
        }
        return { url };
      },
    });
    mapRef.current = map;
    // interleaved: deck.gl layers are inserted into MapLibre's own layer stack
    // and share its WebGL2 context + depth buffer, so 3D Tiles are correctly
    // occluded by the terrain instead of always drawing on top.
    const overlay = new MapboxOverlay({ layers: [], interleaved: true });
    overlayRef.current = overlay;
    map.addControl(overlay);
    map.on("load", () => {
      styleLoadedRef.current = true;
      map.addSource(HIGHLIGHT_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: HIGHLIGHT_ID,
        type: "line",
        source: HIGHLIGHT_ID,
        paint: { "line-color": "#ef4444", "line-width": 3 },
      });
      applyLayers(map, layersRef.current, appliedRef.current, clickHandlersRef.current, (r) =>
        onFeatureClickRef.current?.(r),
      );
      applyDeckLayers(
        overlay,
        layersRef.current,
        handleTilesetLoad,
        getAuthTokenRef.current,
        getCoreUrlRef.current,
      );
      applyTerrain(map, terrainRef.current);
      // `once()` est typé `this | Promise<any>` côté maplibre-gl (le
      // second membre de l'union ne s'applique que si aucun listener n'est
      // fourni — ici il y en a un, le retour réel est toujours `this`,
      // jamais une Promise) : `void` neutralise le faux positif de type
      // sans changer de comportement.
      void map.once("idle", () => {
        idleRef.current = true;
        maybeFireReady();
      });
    });
    map.on("moveend", () => {
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      const bounds = map.getBounds().toArray().flat() as [number, number, number, number];
      cb({
        center: [c.lng, c.lat],
        zoom: map.getZoom(),
        bbox: bounds,
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      });
    });
    return () => {
      map.removeControl(overlay);
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
      styleLoadedRef.current = false;
      idleRef.current = false;
      readyFiredRef.current = false;
      // La règle suggère de copier la ref dans une variable locale au
      // montage pour éviter qu'elle "ait changé" au nettoyage — mais c'est
      // précisément le comportement voulu ici : cet effet ne monte/démonte
      // qu'une fois (cf. dépendances [] ci-dessous), et on veut vider
      // l'ensemble accumulé sur toute la durée de vie du composant, pas un
      // instantané pris au montage.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      loadedTilesetsRef.current.clear();
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const overlay = overlayRef.current;
    if (!map || !styleLoadedRef.current || !overlay) return;
    applyLayers(map, config.layers, appliedRef.current, clickHandlersRef.current, (r) =>
      onFeatureClickRef.current?.(r),
    );
    applyDeckLayers(
      overlay,
      config.layers,
      handleTilesetLoad,
      getAuthTokenRef.current,
      getCoreUrlRef.current,
    );
  }, [config.layers, handleTilesetLoad]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    applyTerrain(map, config.terrain);
  }, [config.terrain]);

  useImperativeHandle(
    ref,
    () => ({
      flyTo: (opts) => {
        mapRef.current?.flyTo(opts);
      },
      highlight: (geometry) => {
        const src = mapRef.current?.getSource(HIGHLIGHT_ID) as
          { setData?: (d: unknown) => void } | undefined;
        src?.setData?.(
          geometry
            ? { type: "Feature", geometry, properties: {} }
            : { type: "FeatureCollection", features: [] },
        );
      },
    }),
    [],
  );

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map-container" />
      {!hideLegend && <MapLegend layers={config.layers} />}
    </div>
  );
});
