// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useInstanceInfo, useItem, useMapConfig, useSaveMap } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { MapConfig, MapLayer, MapTerrainConfig, PrintLayoutConfig } from "../api/types";
import { hasPermission } from "../auth/permissions";
import { buildLegend, symbologyToPaintInputs } from "../builder/widgets/mapSymbology";
import { MapSymbologyLegend } from "../map/MapSymbologyLegend";
import type { MapViewHandle } from "../map/MapView";
// Lazy, comme mapWidget.tsx/ExplorerDrawer.tsx : un import statique ici
// neutralisait leur propre lazy() de MapView (Rollup ne peut isoler un
// module dans son propre chunk tant qu'un site l'importe statiquement),
// visible au build via le warning INEFFECTIVE_DYNAMIC_IMPORT (GAP-68).
const MapView = lazy(() => import("../map/MapView").then((m) => ({ default: m.MapView })));
// REV-102 : lazy, hors charge initiale (marge de bundle).
const AddressSearch = lazy(() =>
  import("../map/AddressSearch").then((m) => ({ default: m.AddressSearch })),
);
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { TerrainPanel } from "../map/TerrainPanel";
import { CameraControls } from "../map/CameraControls";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { ExportPanel } from "../builder/print/ExportPanel";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { isConflictError } from "../api/ApiError";
import { SaveConflictNotice } from "../builder/SaveConflictNotice";
import { Button } from "../ui/kit/Button";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";
import { useDirtyGuard } from "../lib/useDirtyGuard";
import { useUrlSyncedState } from "../lib/useUrlSyncedState";
import { t } from "../i18n";
import { LoadingState } from "../ui/kit/LoadingState";
import { QueryErrorState } from "../ui/kit/QueryErrorState";

const MAP_TABS = ["layers", "map", "settings"];

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
  // SP-B6c : dérivé localement, pas comparé au serveur (design retenu au
  // brief) — mis à `true` par `updateDraft` (wrapper unique autour de
  // `setDraft`, utilisé sur tous les points de mutation du brouillon
  // ci-dessous), remis à `false` dans l'`onSuccess` de la sauvegarde. La
  // synchronisation initiale depuis `query.data` (effet ci-dessous) passe
  // volontairement par le `setDraft` brut : ce n'est pas une modification de
  // l'utilisateur, et le même effet se redéclenche après une sauvegarde
  // réussie (invalidation de la query), ce qui re-marquerait le brouillon
  // sale immédiatement après l'avoir marqué propre si on passait par
  // `updateDraft` ici.
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  // REV-207 : onglet actif du triptyque restauré depuis l'URL. Valeur inconnue
  // → onglet « map » par défaut.
  const [tabParam, setTabParam] = useUrlSyncedState<string>("tab", null);
  const activeTab = tabParam !== null && MAP_TABS.includes(tabParam) ? tabParam : "map";
  const updateDraft: typeof setDraft = (next) => {
    setHasUnsavedChanges(true);
    setDraft(next);
  };
  const { ConfirmLeaveDialog } = useDirtyGuard(hasUnsavedChanges);
  const baseVersionRef = useRef<number | undefined>(undefined);
  const versionSeededRef = useRef(false);
  const mapViewRef = useRef<MapViewHandle>(null);
  const hasAutoFitted = useRef(false);
  // C1 (revue finale) : `onReady` (MapView.tsx:1017-1033/1063) ne se
  // déclenche qu'une fois la carte réellement prête (idle) — c'est le seul
  // signal fiable que `mapViewRef.current` est non-null, y compris quand le
  // chunk lazy de MapView n'a pas encore fini de charger. Sans lui, l'effet
  // d'auto-cadrage ci-dessous pouvait poser `hasAutoFitted.current = true`
  // avant même que `fitBounds` ait pu s'exécuter (no-op via `?.`), et ne se
  // redéclenchait jamais une fois le chunk chargé.
  const [mapReady, setMapReady] = useState(false);
  const isExportRender = useIsExportRender();
  const instanceQuery = useInstanceInfo();
  const exportEnabled = instanceQuery.data?.exportEnabled === true;

  useEffect(() => {
    // Seed unique (REV-271) : un refetch (retour d'onglet) ne doit ni écraser
    // le brouillon ni rebaser la version — sinon le 412 ne se déclenche jamais.
    if (query.data && !versionSeededRef.current) {
      versionSeededRef.current = true;
      setDraft(query.data);
      baseVersionRef.current = query.data.baseVersion;
    }
  }, [query.data]);

  // D18 : n'auto-cadrer que si la vue est encore la valeur par défaut
  // littérale posée à la création (layers.ts:43) — jamais écraser un
  // cadrage que l'utilisateur a explicitement enregistré. Le bouton manuel
  // "Ajuster à l'emprise des données" (ci-dessous) reste la voie pour
  // re-déclencher l'ajustement dans les autres cas.
  useEffect(() => {
    if (hasAutoFitted.current) return;
    if (!mapReady) return;
    if (!draft) return;
    const isDefaultView =
      draft.view.center[0] === 2.4 && draft.view.center[1] === 46.6 && draft.view.zoom === 5;
    if (!isDefaultView) return;
    const bbox = itemQuery.data?.bbox;
    if (!bbox) return;
    const view = mapViewRef.current;
    if (!view) return;
    hasAutoFitted.current = true;
    view.fitBounds(bbox);
  }, [draft, itemQuery.data?.bbox, mapReady]);

  // `draft` lags one render behind a successful load (it is synced in the
  // effect above), so keep showing the loader during that gap instead of
  // flashing the error.
  if (query.isLoading || itemQuery.isLoading || (!draft && !query.isError)) return <LoadingState />;
  if (query.isError || itemQuery.isError || !draft || !itemQuery.data)
    return (
      <QueryErrorState queries={[query, itemQuery]} notFoundMessage={t("mapEditor.notFound")} />
    );

  const setLayers = (layers: MapLayer[]) => updateDraft({ ...draft, layers });
  const setStyle = (style: string) => updateDraft({ ...draft, basemap: { style } });
  const setView = (view: {
    center: [number, number];
    zoom: number;
    pitch: number;
    bearing: number;
  }) => updateDraft((d) => (d ? { ...d, view } : d));
  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    updateDraft((d) => (d ? { ...d, printLayout } : d));
  }
  function setTerrain(terrain: MapTerrainConfig | null) {
    updateDraft((d) => (d ? { ...d, terrain } : d));
  }
  const currentDraft = draft;
  function goToAddress(center: [number, number]) {
    updateDraft((d) => (d ? { ...d, view: { ...d.view, center, zoom: 16 } } : d));
    mapViewRef.current?.flyTo({ center, zoom: 16 });
  }

  function setCamera(next: { pitch: number; bearing: number }) {
    updateDraft((d) => (d ? { ...d, view: { ...d.view, ...next } } : d));
    mapViewRef.current?.flyTo(
      { center: currentDraft.view.center, zoom: currentDraft.view.zoom, ...next },
      true,
    );
  }

  // Export/print chrome (SP-17a Task 10): the Playwright worker (Task 6)
  // navigates here with ?exportRender=1 to capture a clean shot of the map
  // plus the PrintLayoutConfig overlays — no builder aside, no editor UI, no
  // triptyque chrome. Ready signal = MapLibre "idle" (map.once), relayed via
  // MapView's onReady. showScaleBar/showNorthArrow were removed entirely
  // from the schema (REV-128) — never rendered, authorable-but-inert.
  // gs-raw-color-ok: bg-white/90 stays hardcoded here on purpose (a print artifact meant to
  // look like paper, not UI chrome — spec §2.2, the map itself also always
  // stays light regardless of ambiance).
  if (isExportRender) {
    return (
      <div className="relative h-full w-full">
        <Suspense fallback={<div className="text-xs text-ink-3">Carte…</div>}>
          <MapView
            config={draft}
            onReady={() => {
              markExportReady();
              setMapReady(true);
            }}
            hideLegend
            getAuthToken={client.getAuthToken}
            getCoreUrl={client.getCoreUrl}
            loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
          />
        </Suspense>
        {draft.printLayout?.title && (
          // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
          <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">
            {draft.printLayout.title}
          </div>
        )}
        {draft.printLayout?.showLegend && (
          // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
          <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.layers
              .filter((l) => l.visible)
              .map((l) => (
                <li key={l.id}>{l.title}</li>
              ))}
          </ul>
        )}
        {draft.printLayout?.cartouche && (
          // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
          <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.printLayout.cartouche}
          </div>
        )}
      </div>
    );
  }

  const isConflict = isConflictError(save.error);
  async function reloadLatest() {
    const latest = await client.getMapConfig(pk);
    setDraft(latest);
    baseVersionRef.current = latest.baseVersion;
    setHasUnsavedChanges(false);
    save.reset();
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{t("docTitle.map")}</h1>
      <TriptychLayout
        activeTabId={activeTab}
        onActiveTabChange={setTabParam}
        browse={{
          id: "layers",
          label: t("mapEditor.layersLabel"),
          content: (
            <div className="p-3">
              <LayersPanel layers={draft.layers} onChange={setLayers} />
            </div>
          ),
        }}
        work={{
          id: "map",
          label: t("mapEditor.mapLabel"),
          content: (
            <div className="relative h-full w-full">
              <Suspense fallback={<div className="text-xs text-ink-3">Carte…</div>}>
                <MapView
                  ref={mapViewRef}
                  config={draft}
                  onViewChange={setView}
                  onReady={() => setMapReady(true)}
                  interactiveTools
                  getAuthToken={client.getAuthToken}
                  getCoreUrl={client.getCoreUrl}
                  loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
                />
              </Suspense>
              {/* Correctif revue Tâche 35 : `MapView` affiche déjà, dans ce même
                  conteneur `relative`, `MapLegend` ancrée `bottom-2 left-2`
                  (noms de couches, actif ici car `hideLegend` n'est passé que
                  sur le chemin export). Ce bloc doit donc occuper un coin
                  distinct — bas-droite, cohérent avec l'unique instance de
                  `MapSymbologyLegend` déjà auto-positionnée à cet endroit
                  dans `mapWidget.tsx` — plutôt que reprendre bas-gauche, qui
                  superposait exactement les deux légendes. `variant="static"`
                  sur chaque enfant retire son propre `absolute` (qui, sorti
                  du flux, ignorait de toute façon le `flex-col`/`gap` de ce
                  conteneur et aurait empilé plusieurs couches au même point)
                  pour laisser ce conteneur gérer position et empilement. */}
              <div
                data-testid="map-symbology-legend-panel"
                className="pointer-events-none absolute bottom-2 right-2 z-10 flex flex-col gap-2"
              >
                {draft.layers
                  .filter(
                    (l): l is Extract<MapLayer, { kind: "vector" }> =>
                      l.kind === "vector" && l.visible,
                  )
                  .map((l) => {
                    if (!l.symbology) return null;
                    const { encodings, colorDomain, sizeDomain, palette, stroke } =
                      symbologyToPaintInputs(l.symbology, undefined);
                    const legend = buildLegend(
                      encodings,
                      colorDomain,
                      sizeDomain,
                      l.geometryKind ?? "polygon",
                      palette,
                      { stroke, icon: l.symbology.icon },
                    );
                    return legend ? (
                      <MapSymbologyLegend key={l.id} legend={legend} variant="static" />
                    ) : null;
                  })}
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: t("mapEditor.inspectLabel"),
          content: (
            <div className="flex flex-col gap-4 p-3">
              <BasemapSelect value={draft.basemap.style} onChange={setStyle} />
              <TerrainPanel value={draft.terrain ?? null} onChange={setTerrain} />
              <Suspense fallback={null}>
                <AddressSearch onSelect={goToAddress} />
              </Suspense>
              <CameraControls
                pitch={draft.view.pitch ?? 0}
                bearing={draft.view.bearing ?? 0}
                onChange={setCamera}
              />
              <Button
                variant="outline"
                size="sm"
                className="w-fit"
                disabled={!itemQuery.data?.bbox}
                onClick={() => {
                  const bbox = itemQuery.data?.bbox;
                  if (bbox) mapViewRef.current?.fitBounds(bbox);
                }}
              >
                {t("mapEditor.fitToDataButton")}
              </Button>
              <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
              <ConfigHistoryPanel
                pk={pk}
                currentVersion={null}
                onRestored={async () => {
                  const restored = await client.getMapConfig(pk);
                  updateDraft(restored);
                  baseVersionRef.current = restored.baseVersion;
                }}
              />
              {exportEnabled && <ExportPanel itemId={pk} />}
              <Button
                size="sm"
                className="w-fit"
                disabled={save.isPending || readOnly}
                onClick={() =>
                  save.mutate(
                    { ...draft, baseVersion: baseVersionRef.current },
                    {
                      onSuccess: (version) => {
                        baseVersionRef.current = version;
                        setHasUnsavedChanges(false);
                      },
                    },
                  )
                }
              >
                {t("common.save")}
              </Button>
              {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
              {save.isError && !isConflict && (
                <p role="alert" className="text-sm text-danger">
                  {t("actions.saveFailed")}
                </p>
              )}
              {isConflict && <SaveConflictNotice onReload={() => void reloadLatest()} />}
            </div>
          ),
        }}
      />
      <ConfirmLeaveDialog />
    </div>
  );
}
