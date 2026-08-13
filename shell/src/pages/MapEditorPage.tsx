// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useInstanceInfo, useMapConfig, useSaveMap } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { MapConfig, MapLayer, MapTerrainConfig, PrintLayoutConfig } from "../api/types";
import { MapView, type MapViewHandle } from "../map/MapView";
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { TerrainPanel } from "../map/TerrainPanel";
import { CameraControls } from "../map/CameraControls";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { ExportPanel } from "../builder/print/ExportPanel";
import { Button } from "../ui/button";
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";

export function MapEditorPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const query = useMapConfig(pk);
  const save = useSaveMap(pk);
  const [draft, setDraft] = useState<MapConfig | null>(null);
  const mapViewRef = useRef<MapViewHandle>(null);
  const isExportRender = useIsExportRender();
  const instanceQuery = useInstanceInfo();
  const exportEnabled = instanceQuery.data?.exportEnabled === true;

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
  const setView = (view: { center: [number, number]; zoom: number; pitch: number; bearing: number }) =>
    setDraft((d) => (d ? { ...d, view } : d));
  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    setDraft((d) => (d ? { ...d, printLayout } : d));
  }
  function setTerrain(terrain: MapTerrainConfig | null) {
    setDraft((d) => (d ? { ...d, terrain } : d));
  }
  const currentDraft = draft;
  function setCamera(next: { pitch: number; bearing: number }) {
    setDraft((d) => (d ? { ...d, view: { ...d.view, ...next } } : d));
    mapViewRef.current?.flyTo({ center: currentDraft.view.center, zoom: currentDraft.view.zoom, ...next });
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
        <MapView config={draft} onReady={markExportReady} hideLegend getAuthToken={client.getAuthToken} />
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
        <TerrainPanel value={draft.terrain ?? null} onChange={setTerrain} />
        <CameraControls pitch={draft.view.pitch ?? 0} bearing={draft.view.bearing ?? 0} onChange={setCamera} />
        <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
        {exportEnabled && <ExportPanel itemId={pk} />}
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
        <MapView ref={mapViewRef} config={draft} onViewChange={setView} getAuthToken={client.getAuthToken} />
      </div>
    </div>
  );
}
