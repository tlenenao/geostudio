// SPDX-License-Identifier: Apache-2.0
// AppConfig synthétisés en mémoire pour les items publiés sans `layout`
// (map, dataset) — jamais persistés : un seul runtime AppRenderer (règle 3).
import type { AppConfig, BaseMap, MapLayer, MapTerrainConfig, MapViewport } from "../types";

export function datasetPreviewConfig(collectionId: string, attachmentField?: string): AppConfig {
  const dataSourceId = "dataset-preview";
  return {
    kind: "app",
    theme: {},
    dataSources: [
      { id: dataSourceId, type: "features", service: "core", layer: collectionId, query: {} },
    ],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "dataset-preview-map",
          widget: "map",
          ordinal: 1,
          x: 0,
          y: 0,
          w: 6,
          h: 6,
          props: {
            dataSourceId,
            ...(attachmentField ? { popup: { attachmentField } } : {}),
          },
        },
        {
          id: "dataset-preview-table",
          widget: "table",
          ordinal: 1,
          x: 6,
          y: 0,
          w: 6,
          h: 6,
          props: { dataSourceId, columns: [], pageSize: 10 },
        },
      ],
    },
  };
}

export function mapRuntimeConfig(map: {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  terrain?: MapTerrainConfig | null;
}): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "public-map",
          widget: "map",
          ordinal: 1,
          x: 0,
          y: 0,
          w: 12,
          h: 12,
          props: {
            layers: map.layers,
            basemapStyle: map.basemap.style,
            center: map.view.center,
            zoom: map.view.zoom,
            cameraPitch: map.view.pitch ?? 0,
            cameraBearing: map.view.bearing ?? 0,
            terrain: map.terrain ?? null,
          },
        },
      ],
    },
  };
}
