// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";
import { Button } from "../ui/button";

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
  const { data, isLoading, isError, refetch } = useLayerSources({ q: q || undefined });

  function addTiles3D() {
    if (!tiles3dTitle.trim() || !tiles3dUrl.trim()) return;
    onAdd({ id: crypto.randomUUID(), title: tiles3dTitle, visible: true, kind: "tiles3d", url: tiles3dUrl });
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
        className="h-8 rounded-md border border-slate-300 px-2 text-sm"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {isLoading && <p className="text-sm text-slate-500">Chargement des sources…</p>}
      {isError && (
        <div className="text-sm text-red-600">
          <p role="alert">Impossible de charger les sources de couches.</p>
          <button type="button" className="underline" onClick={() => refetch()}>
            Réessayer
          </button>
        </div>
      )}
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-slate-500">Aucune source disponible.</p>
      )}
      {!isLoading && !isError && data && data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.map((source) => (
            <li key={`${source.service}:${source.id}`}>
              <button
                type="button"
                className="w-full rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100"
                onClick={() => onAdd(toMapLayer(source))}
              >
                {source.title}
                <span className="ml-2 text-xs text-slate-400">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-slate-400">
                    {source.featureCount} entités
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-slate-500">Ajouter un tileset 3D par URL</p>
        <div className="flex flex-col gap-1">
          <input
            aria-label="Titre du tileset 3D"
            type="text"
            placeholder="Titre"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
            value={tiles3dTitle}
            onChange={(e) => setTiles3dTitle(e.target.value)}
          />
          <input
            aria-label="URL du tileset.json"
            type="text"
            placeholder="https://…/tileset.json"
            className="h-8 rounded-md border border-slate-300 px-2 text-sm"
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
    </div>
  );
}
