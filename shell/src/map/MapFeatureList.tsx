// SPDX-License-Identifier: Apache-2.0
// AUD-114 (WCAG 2.1.1) : la sélection d'une entité ne passe plus seulement par le clic sur le
// canvas — cette liste des entités rendues dans la vue ouvre le même popup, au clavier.
import { useId, useState } from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { t } from "../i18n";
import "../i18n/domains/map";

type Item = {
  key: string;
  label: string;
  layerId: string;
  properties: Record<string, unknown>;
  lngLat: { lng: number; lat: number };
  id: string | number | undefined;
};

const MAX_ITEMS = 50;
const NAME_KEYS = ["name", "nom", "title", "titre", "label", "libelle"];

function labelOf(properties: Record<string, unknown>, id: unknown): string {
  for (const k of NAME_KEYS) {
    const v = Object.entries(properties).find(([pk]) => pk.toLowerCase() === k)?.[1];
    if (typeof v === "string" && v) return v;
  }
  return id != null ? String(id) : t("mapFeatureList.unnamed");
}

function anchor(
  geometry: GeoJSON.Geometry,
  fallback: { lng: number; lat: number },
): { lng: number; lat: number } {
  if (geometry.type === "Point") {
    return { lng: geometry.coordinates[0], lat: geometry.coordinates[1] };
  }
  return fallback;
}

/** Entités rendues dans la vue, rattachées à leur couche de config (sous-couches `id__x` incluses). */
export function collectViewFeatures(
  map: MapLibreMap,
  popupLayerIds: string[],
  max = MAX_ITEMS,
): Item[] {
  const center = map.getCenter();
  const seen = new Set<string>();
  const items: Item[] = [];
  for (const f of map.queryRenderedFeatures()) {
    const layerId = popupLayerIds.find(
      (id) => f.layer.id === id || f.layer.id.startsWith(`${id}__`),
    );
    if (!layerId) continue;
    const properties = (f.properties ?? {}) as Record<string, unknown>;
    if ("point_count" in properties) continue; // cellule/cluster, pas une entité
    const key = `${layerId}:${f.id ?? JSON.stringify(properties)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({
      key,
      label: labelOf(properties, f.id),
      layerId,
      properties,
      lngLat: anchor(f.geometry, { lng: center.lng, lat: center.lat }),
      id: f.id,
    });
    if (items.length >= max) break;
  }
  return items;
}

export function MapFeatureList({
  map,
  popupLayerIds,
  onSelect,
}: {
  map: MapLibreMap;
  popupLayerIds: string[];
  onSelect: (item: Item) => void;
}) {
  const [items, setItems] = useState<Item[] | null>(null);
  const panelId = useId();
  const open = items !== null;
  return (
    <div className="absolute left-2 top-2 z-10 flex max-w-[16rem] flex-col gap-1 text-xs">
      <button
        type="button"
        className="self-start rounded border border-control bg-surface px-2 py-1 text-ink"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setItems(open ? null : collectViewFeatures(map, popupLayerIds))}
      >
        {t("mapFeatureList.toggle")}
      </button>
      <div id={panelId} hidden={!open}>
        {items &&
          (items.length === 0 ? (
            <p className="rounded bg-surface p-2 text-ink-2">{t("mapFeatureList.empty")}</p>
          ) : (
            <ul
              aria-label={t("mapFeatureList.toggle")}
              className="max-h-48 overflow-auto rounded border border-rule bg-surface"
            >
              {items.map((it) => (
                <li key={it.key}>
                  <button
                    type="button"
                    className="w-full px-2 py-1 text-left text-ink hover:bg-raised"
                    onClick={() => onSelect(it)}
                  >
                    {it.label}
                  </button>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </div>
  );
}
