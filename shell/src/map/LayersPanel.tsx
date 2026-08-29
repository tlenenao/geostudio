// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { MapLayer } from "../api/types";
import { LayerPicker } from "./LayerPicker";
import { MapSymbologyEditor } from "./MapSymbologyEditor";
import { PopupEditor } from "./PopupEditor";

// Charge le schéma de la collection sous-jacente pour offrir la liste des
// champs à l'auteur — patron déjà établi par CrossFilterLinkEditor.tsx:28-34
// (useQuery inline, pas de hook dédié dans api/hooks.ts pour ce besoin).
function LayerPopupEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const client = useItemClient();
  const collectionId = layer.kind === "vector" ? layer.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: Boolean(collectionId),
  });
  return (
    <PopupEditor
      value={layer.popup}
      // Sans collectionId (tuiles externes, couche GeoJSON), la liste est
      // vide et l'auteur saisit les noms de champs à la main : PopupEditor
      // gère les deux cas avec le même contrôle.
      availableFields={schema.data?.fields.map((f) => f.name) ?? []}
      onChange={(popup) => onChangeLayer({ ...layer, popup })}
    />
  );
}

// Même patron que LayerPopupEditor ci-dessus. Sans collectionId (tuiles
// externes, couche GeoJSON "feature"), il n'y a pas de collection
// interrogeable pour runStatistics ici : la couche "feature" du widget
// carte (mapWidget.tsx, Task 10) résout à travers son propre datasetId,
// chemin distinct et non unifié avec celui-ci (spec §1).
function LayerSymbologyEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const client = useItemClient();
  const collectionId = layer.kind === "vector" ? layer.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: Boolean(collectionId),
  });
  if (!collectionId) return null; // external tiles / plain GeoJSON feature layer: no collection to query
  return (
    <MapSymbologyEditor
      value={layer.symbology}
      availableFields={schema.data?.fields.map((f) => f.name) ?? []}
      themeColors={undefined} // no Theme on a standalone MapConfig (spec §1)
      runStatistics={(query) =>
        client.queryDataSource({
          id: `map-symbology-${collectionId}`,
          type: "statistics",
          service: "core",
          layer: collectionId,
          query,
        })
      }
      sampleField={(field, limit) => client.sampleCollectionField(collectionId, field, limit)}
      // `?.()` OBLIGATOIRE, pas cosmétique (défaut n° 5 de la brief Task 12) :
      // ce hôte est rendu dans des tests existants avec des ItemClient
      // PARTIELS (LayersPanel.test.tsx:48 et :103). Sans `?.`,
      // `client.listMapIcons()` lève SYNCHRONIQUEMENT dans le callback
      // d'effet et fait échouer le rendu de ces tests, verts aujourd'hui —
      // le `.catch()` de l'effet n'attrape rien, il n'y a pas encore de
      // promesse.
      listCustomIcons={() => client.listMapIcons?.() ?? Promise.resolve([])}
      uploadCustomIcon={(file, title, category) =>
        // UN SEUL appel (D7) : plus de presign → PUT → POST. Le cœur reçoit
        // les octets, choisit la clé S3, assainit, puis écrit.
        client.uploadMapIcon(file, title, category)
      }
      deleteCustomIcon={(id) => client.deleteMapIcon(id)}
      onChange={(symbology) => onChangeLayer({ ...layer, symbology })}
    />
  );
}

export function LayersPanel({
  layers,
  onChange,
}: {
  layers: MapLayer[];
  onChange: (layers: MapLayer[]) => void;
}) {
  function toggle(id: string) {
    onChange(layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)));
  }
  function remove(id: string) {
    onChange(layers.filter((l) => l.id !== id));
  }
  function move(index: number, delta: number) {
    const next = index + delta;
    if (next < 0 || next >= layers.length) return;
    const copy = [...layers];
    [copy[index], copy[next]] = [copy[next], copy[index]];
    onChange(copy);
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-1">
        {layers.map((layer, i) => (
          <li key={layer.id} className="flex items-center gap-2 text-sm">
            <span className="flex-1 truncate">{layer.title}</span>
            <button
              type="button"
              aria-label={`Monter ${layer.title}`}
              disabled={i === 0}
              className="px-1 disabled:opacity-30"
              onClick={() => move(i, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              aria-label={`Descendre ${layer.title}`}
              disabled={i === layers.length - 1}
              className="px-1 disabled:opacity-30"
              onClick={() => move(i, 1)}
            >
              ↓
            </button>
            <button
              type="button"
              aria-label={`${layer.visible ? "Masquer" : "Afficher"} ${layer.title}`}
              className="px-1"
              onClick={() => toggle(layer.id)}
            >
              {layer.visible ? "👁" : "🚫"}
            </button>
            <button
              type="button"
              aria-label={`Retirer ${layer.title}`}
              className="px-1 text-red-600"
              onClick={() => remove(layer.id)}
            >
              ✕
            </button>
            {(layer.kind === "vector" || layer.kind === "feature") && (
              <div className="basis-full pl-2">
                <LayerPopupEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
                <LayerSymbologyEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
              </div>
            )}
          </li>
        ))}
        {layers.length === 0 && <li className="text-xs text-slate-400">Aucune couche.</li>}
      </ul>
      <div className="border-t pt-2">
        <p className="mb-1 text-xs font-medium text-slate-500">Ajouter une couche</p>
        <LayerPicker onAdd={(layer) => onChange([...layers, layer])} />
      </div>
    </div>
  );
}
