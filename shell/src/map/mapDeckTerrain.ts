// SPDX-License-Identifier: Apache-2.0
import * as maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { HeatmapLayer, HexagonLayer } from "@deck.gl/aggregation-layers";
import { ColumnLayer } from "@deck.gl/layers";
import { Tile3DLayer } from "@deck.gl/geo-layers";
import { Tiles3DLoader } from "@loaders.gl/3d-tiles";
import type { MapConfig } from "../api/types";
import { isHostedTilesetUrl } from "./hostedCoreUrl";

export const TERRAIN_SOURCE_ID = "__terrain__";

export type DeckLayer = Extract<MapConfig["layers"][number], { kind: "deck" }>;
export type Tiles3DMapLayer = Extract<MapConfig["layers"][number], { kind: "tiles3d" }>;

export function buildDeckLayer(layer: DeckLayer) {
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
export function tilesetKey(layer: Tiles3DMapLayer) {
  return `${layer.id}\n${layer.url}`;
}

export function buildTiles3DLayer(
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

export function applyDeckLayers(
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
// P30.01 (t03-012) : deck.gl interleaved attache un device luma au contexte WebGL
// de MapLibre et ne détruit jamais son CanvasContext ; l'écouteur `matchMedia`
// de résolution (DPR) qu'il pose reste alors accroché globalement et retient le
// canvas, donc tout le DOM détaché de l'éditeur (~380 nœuds par ouverture).
// ponytail: accès à `gl.luma` (détail interne de luma.gl 9) ; à retirer si
// deck.gl détruit lui-même ce contexte à `MapboxOverlay.onRemove`.
// REV-293 : en `vite dev`, StrictMode double-monte MapView ; une croissance
// résiduelle y a été mesurée (cf. .superpowers/sdd/backlogB-L5a-293-mesure.txt),
// absente du build de production (e2e/map-editor-leak.spec.ts). Acceptée :
// chaque montage a sa propre carte, la libération n'est appelée qu'une fois
// par carte — une garde d'idempotence (WeakSet) n'y changerait rien.
export function releaseLumaCanvasObserver(map: maplibregl.Map): void {
  try {
    const gl = map.getCanvas().getContext("webgl2") as {
      luma?: { device?: { canvasContext?: { destroy?: () => void } } };
    } | null;
    gl?.luma?.device?.canvasContext?.destroy?.();
  } catch {
    // Libération best-effort : un échec ne doit jamais empêcher map.remove().
  }
}

export function applyTerrain(
  map: maplibregl.Map,
  terrain: MapConfig["terrain"] | null | undefined,
) {
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
