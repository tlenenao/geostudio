import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";

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
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
}

export function LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const { data, isLoading, isError, refetch } = useLayerSources();

  if (isLoading) return <p className="text-sm text-slate-500">Chargement des sources…</p>;
  if (isError) {
    return (
      <div className="text-sm text-red-600">
        <p role="alert">Impossible de charger les sources de couches.</p>
        <button type="button" className="underline" onClick={() => refetch()}>
          Réessayer
        </button>
      </div>
    );
  }
  if (!data || data.length === 0) {
    return <p className="text-sm text-slate-500">Aucune source disponible.</p>;
  }
  return (
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
          </button>
        </li>
      ))}
    </ul>
  );
}
