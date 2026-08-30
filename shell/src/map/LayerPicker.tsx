// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";
import { detectGeometryKind, renderAsFor } from "../builder/widgets/mapSymbology";
import { fetchFeatureCollection } from "./geojsonIntrospect";
import { Button } from "../ui/kit/Button";

function toMapLayer(source: LayerSource): MapLayer {
  const id = crypto.randomUUID();
  if (source.kind === "vector") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "vector",
      tilesUrl: source.tilesUrl ?? "",
      sourceLayer: source.sourceLayer ?? "",
      collectionId: source.collectionId,
      geometryKind: source.geometryKind,
      pkColumn: source.pkColumn,
    };
  }
  if (source.kind === "raster") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "raster",
      tilesUrl: source.tilesUrl ?? "",
      opacity: 1,
    };
  }
  if (source.kind === "tiles3d") {
    return { id, title: source.title, visible: true, kind: "tiles3d", url: source.url ?? "" };
  }
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
}

export function LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const [q, setQ] = useState("");
  const [tiles3dTitle, setTiles3dTitle] = useState("");
  const [tiles3dUrl, setTiles3dUrl] = useState("");
  const [featureTitle, setFeatureTitle] = useState("");
  const [featureUrl, setFeatureUrl] = useState("");
  const [featureError, setFeatureError] = useState<string | null>(null);
  const [featureBusy, setFeatureBusy] = useState(false);
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useLayerSources({ q: q || undefined });

  async function addFeatureLayer() {
    const title = featureTitle.trim();
    const url = featureUrl.trim();
    if (!title || !url) return;
    setFeatureBusy(true);
    setFeatureError(null);
    let renderAs: "fill" | "circle" | "line" | undefined;
    try {
      const fc = await fetchFeatureCollection(url);
      renderAs = renderAsFor(detectGeometryKind(fc.features[0]?.geometry));
      // Amorce le cache que LayersPanel.tsx lit sous la même clé
      // (useFeatureLayerGeoJson) : ouvrir tout de suite le panneau de
      // symbologie de cette couche ne refait pas ce fetch.
      queryClient.setQueryData(["feature-geojson", url], fc);
    } catch {
      // L'URL est ajoutée quand même : la même URL, si elle échoue ici
      // (CORS, en-têtes différents...), échouera de la même façon pour
      // MapLibre au rendu — ce n'est pas une régression, juste un défaut
      // qu'on ne peut pas prédire sans que MapView tente lui-même le rendu.
      setFeatureError(
        "Couche ajoutée, mais son contenu n'a pas pu être vérifié (l'URL sera quand même utilisée pour l'affichage).",
      );
    }
    onAdd({
      id: crypto.randomUUID(),
      title,
      visible: true,
      kind: "feature",
      url,
      ...(renderAs ? { renderAs } : {}),
    });
    setFeatureTitle("");
    setFeatureUrl("");
    setFeatureBusy(false);
  }

  function addTiles3D() {
    if (!tiles3dTitle.trim() || !tiles3dUrl.trim()) return;
    onAdd({
      id: crypto.randomUUID(),
      title: tiles3dTitle,
      visible: true,
      kind: "tiles3d",
      url: tiles3dUrl,
    });
    setTiles3dTitle("");
    setTiles3dUrl("");
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        type="search"
        role="searchbox"
        aria-label="Rechercher une source de couche"
        placeholder="Rechercher…"
        className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {isLoading && <p className="text-sm text-ink-2">Chargement des sources…</p>}
      {isError && (
        <div className="text-sm text-danger">
          <p role="alert">Impossible de charger les sources de couches.</p>
          <button type="button" className="underline" onClick={() => void refetch()}>
            Réessayer
          </button>
        </div>
      )}
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-ink-2">Aucune source disponible.</p>
      )}
      {!isLoading && !isError && data && data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.map((source) => (
            <li key={`${source.service}:${source.id}`}>
              <button
                type="button"
                className="w-full rounded-md px-2 py-1 text-left text-sm text-ink hover:bg-sunken"
                onClick={() => onAdd(toMapLayer(source))}
              >
                {source.title}
                <span className="ml-2 text-xs text-ink-3">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-ink-3">{source.featureCount} entités</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-ink-2">Ajouter un tileset 3D par URL</p>
        <div className="flex flex-col gap-1">
          <input
            aria-label="Titre du tileset 3D"
            type="text"
            placeholder="Titre"
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={tiles3dTitle}
            onChange={(e) => setTiles3dTitle(e.target.value)}
          />
          <input
            aria-label="URL du tileset.json"
            type="text"
            placeholder="https://…/tileset.json"
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={tiles3dUrl}
            onChange={(e) => setTiles3dUrl(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!tiles3dTitle.trim() || !tiles3dUrl.trim()}
            onClick={addTiles3D}
          >
            Ajouter le tileset 3D
          </Button>
        </div>
      </div>
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-ink-2">Ajouter une couche par URL GeoJSON</p>
        <div className="flex flex-col gap-1">
          <input
            aria-label="Titre de la couche GeoJSON"
            type="text"
            placeholder="Titre"
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={featureTitle}
            onChange={(e) => setFeatureTitle(e.target.value)}
          />
          <input
            aria-label="URL du GeoJSON"
            type="text"
            placeholder="https://…/donnees.geojson"
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={featureUrl}
            onChange={(e) => setFeatureUrl(e.target.value)}
          />
          {featureError && (
            <p role="alert" className="text-xs text-warn">
              {featureError}
            </p>
          )}
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!featureTitle.trim() || !featureUrl.trim() || featureBusy}
            onClick={() => void addFeatureLayer()}
          >
            Ajouter la couche
          </Button>
        </div>
      </div>
    </div>
  );
}
