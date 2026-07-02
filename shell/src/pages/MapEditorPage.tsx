import { useEffect, useState } from "react";
import { useMapConfig, useSaveMap } from "../api/hooks";
import type { MapConfig, MapLayer } from "../api/types";
import { MapView } from "../map/MapView";
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { Button } from "../ui/button";

export function MapEditorPage({ pk }: { pk: string }) {
  const query = useMapConfig(pk);
  const save = useSaveMap(pk);
  const [draft, setDraft] = useState<MapConfig | null>(null);

  useEffect(() => {
    if (query.data) setDraft(query.data);
  }, [query.data]);

  // `draft` lags one render behind a successful load (it is synced in the
  // effect above), so keep showing the loader during that gap instead of
  // flashing the error.
  if (query.isLoading || (!draft && !query.isError)) return <p role="status">Chargement…</p>;
  if (query.isError || !draft)
    return (
      <p role="alert" className="text-sm text-red-600">
        Carte introuvable.
      </p>
    );

  const setLayers = (layers: MapLayer[]) => setDraft({ ...draft, layers });
  const setStyle = (style: string) => setDraft({ ...draft, basemap: { style } });
  const setView = (view: { center: [number, number]; zoom: number }) =>
    setDraft((d) => (d ? { ...d, view } : d));

  return (
    <div className="flex h-full gap-4">
      <aside className="flex w-72 flex-col gap-4 overflow-auto">
        <BasemapSelect value={draft.basemap.style} onChange={setStyle} />
        <LayersPanel layers={draft.layers} onChange={setLayers} />
        <Button size="sm" className="w-fit" disabled={save.isPending} onClick={() => save.mutate(draft)}>
          Enregistrer
        </Button>
        {save.isError && (
          <p role="alert" className="text-sm text-red-600">
            Échec de l'enregistrement.
          </p>
        )}
      </aside>
      <div className="relative flex-1">
        <MapView config={draft} onViewChange={setView} />
      </div>
    </div>
  );
}
