// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useInstanceInfo, useItem, useMapConfig, useSaveMap } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { MapConfig, MapLayer, MapTerrainConfig, PrintLayoutConfig } from "../api/types";
import { hasPermission } from "../auth/permissions";
import { MapView, type MapViewHandle } from "../map/MapView";
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { TerrainPanel } from "../map/TerrainPanel";
import { CameraControls } from "../map/CameraControls";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { ExportPanel } from "../builder/print/ExportPanel";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { Button } from "../ui/kit/Button";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";
import { t } from "../i18n";

export function MapEditorPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const query = useMapConfig(pk);
  const save = useSaveMap(pk);
  const itemQuery = useItem(pk);
  // SP-42/F-shell-pages-04 : cf. commentaire jumeau sur DatasetEditPage.tsx —
  // même doctrine, même résidu documenté (permissions.write incomplet vs
  // garde de privilège de domaine).
  //
  // SP-42, revue finale (point 2, Critical) : `itemQuery.data` est
  // `undefined` pendant tout le chargement ET en cas d'erreur — hasPermission
  // renvoie alors `false`, verrouillant Enregistrer pour la mauvaise raison
  // (pas "lecture seule", "pas encore chargé"). Le garde de rendu ci-dessous
  // inclut désormais itemQuery.isLoading/isError (même patron que
  // DatasetEditPage.tsx:52-58) : `readOnly` n'est calculé qu'une fois l'item
  // effectivement résolu.
  const readOnly = !hasPermission(itemQuery.data, "write");
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
  if (query.isLoading || itemQuery.isLoading || (!draft && !query.isError))
    return <p role="status">Chargement…</p>;
  if (query.isError || itemQuery.isError || !draft || !itemQuery.data)
    return (
      <p role="alert" className="text-sm text-danger">
        Carte introuvable.
      </p>
    );

  const setLayers = (layers: MapLayer[]) => setDraft({ ...draft, layers });
  const setStyle = (style: string) => setDraft({ ...draft, basemap: { style } });
  const setView = (view: {
    center: [number, number];
    zoom: number;
    pitch: number;
    bearing: number;
  }) => setDraft((d) => (d ? { ...d, view } : d));
  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    setDraft((d) => (d ? { ...d, printLayout } : d));
  }
  function setTerrain(terrain: MapTerrainConfig | null) {
    setDraft((d) => (d ? { ...d, terrain } : d));
  }
  const currentDraft = draft;
  function setCamera(next: { pitch: number; bearing: number }) {
    setDraft((d) => (d ? { ...d, view: { ...d.view, ...next } } : d));
    mapViewRef.current?.flyTo({
      center: currentDraft.view.center,
      zoom: currentDraft.view.zoom,
      ...next,
    });
  }

  // Export/print chrome (SP-17a Task 10): the Playwright worker (Task 6)
  // navigates here with ?exportRender=1 to capture a clean shot of the map
  // plus the PrintLayoutConfig overlays — no builder aside, no editor UI, no
  // triptyque chrome. Ready signal = MapLibre "idle" (map.once), relayed via
  // MapView's onReady. showScaleBar/showNorthArrow are intentionally not
  // rendered yet (known limitation, tracked in the Task 10 report — not a
  // silent no-op). bg-white/90 stays hardcoded here on purpose (a print
  // artifact meant to look like paper, not UI chrome — spec §2.2, the map
  // itself also always stays light regardless of ambiance).
  if (isExportRender) {
    return (
      <div className="relative h-full w-full">
        <MapView
          config={draft}
          onReady={markExportReady}
          hideLegend
          getAuthToken={client.getAuthToken}
          getCoreUrl={client.getCoreUrl}
          loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
        />
        {draft.printLayout?.title && (
          <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">
            {draft.printLayout.title}
          </div>
        )}
        {draft.printLayout?.showLegend && (
          <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.layers
              .filter((l) => l.visible)
              .map((l) => (
                <li key={l.id}>{l.title}</li>
              ))}
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
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="map"
        browse={{
          id: "layers",
          label: "Couches",
          content: (
            <div className="p-3">
              <LayersPanel layers={draft.layers} onChange={setLayers} />
            </div>
          ),
        }}
        work={{
          id: "map",
          label: "Carte",
          content: (
            <div className="relative h-full w-full">
              <MapView
                ref={mapViewRef}
                config={draft}
                onViewChange={setView}
                getAuthToken={client.getAuthToken}
                getCoreUrl={client.getCoreUrl}
                loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
              />
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: "Inspecter",
          content: (
            <div className="flex flex-col gap-4 p-3">
              <BasemapSelect value={draft.basemap.style} onChange={setStyle} />
              <TerrainPanel value={draft.terrain ?? null} onChange={setTerrain} />
              <CameraControls
                pitch={draft.view.pitch ?? 0}
                bearing={draft.view.bearing ?? 0}
                onChange={setCamera}
              />
              <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
              <ConfigHistoryPanel
                pk={pk}
                currentVersion={null}
                onRestored={async () => setDraft(await client.getMapConfig(pk))}
              />
              {exportEnabled && <ExportPanel itemId={pk} />}
              <Button
                size="sm"
                className="w-fit"
                disabled={save.isPending || readOnly}
                onClick={() => save.mutate(draft)}
              >
                Enregistrer
              </Button>
              {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
              {save.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de l'enregistrement.
                </p>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
