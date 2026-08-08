// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useMapConfig, useSaveMap } from "../api/hooks";
import type { MapConfig, MapLayer, PrintLayoutConfig } from "../api/types";
import { MapView } from "../map/MapView";
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { Button } from "../ui/button";
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";

export function MapEditorPage({ pk }: { pk: string }) {
  const query = useMapConfig(pk);
  const save = useSaveMap(pk);
  const [draft, setDraft] = useState<MapConfig | null>(null);
  const isExportRender = useIsExportRender();

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
  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    setDraft((d) => (d ? { ...d, printLayout } : d));
  }

  // Export/print chrome (SP-17a Task 10): the Playwright worker (Task 6)
  // navigates here with ?exportRender=1 to capture a clean shot of the map
  // plus the PrintLayoutConfig overlays — no builder aside, no editor UI.
  // Ready signal = MapLibre "idle" (map.once), relayed via MapView's onReady.
  // showScaleBar/showNorthArrow are intentionally not rendered yet (known
  // limitation, tracked in the Task 10 report — not a silent no-op).
  if (isExportRender) {
    return (
      <div className="relative h-full w-full">
        <MapView config={draft} onReady={markExportReady} hideLegend />
        {draft.printLayout?.title && (
          <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">
            {draft.printLayout.title}
          </div>
        )}
        {draft.printLayout?.showLegend && (
          <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.layers.filter((l) => l.visible).map((l) => <li key={l.id}>{l.title}</li>)}
          </ul>
        )}
        {draft.printLayout?.cartouche && (
          <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.printLayout.cartouche}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full gap-4">
      <aside className="flex w-72 flex-col gap-4 overflow-auto">
        <BasemapSelect value={draft.basemap.style} onChange={setStyle} />
        <LayersPanel layers={draft.layers} onChange={setLayers} />
        <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
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
