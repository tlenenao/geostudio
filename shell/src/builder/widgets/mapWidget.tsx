// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useBusAction } from "../ActionBusContext";
import { useSetCrossFilter, useSetExtent } from "../AnalyticsContext";
import { useItemClient } from "../../api/ItemClientProvider";
import {
  buildLegend,
  detectGeometryKind,
  renderAsFor,
  symbologyToPaintInputs,
} from "./mapSymbology";
import type { LayerSymbology } from "./mapSymbology";
import { MapSymbologyLegend } from "../../map/MapSymbologyLegend";
import type { MapConfig, MapTerrainConfig, PopupConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";
import { PopupEditor } from "../../map/PopupEditor";
import { MapSymbologyEditor } from "../../map/MapSymbologyEditor";
import { BasemapSelect } from "../../map/BasemapSelect";
import { TerrainPanel } from "../../map/TerrainPanel";
import { CameraControls } from "../../map/CameraControls";
import { bboxFromFeatureCollection } from "../../lib/geometryBbox";
import { t } from "../../i18n";
import { LayersPanel } from "../../map/LayersPanel";
import type { MapLayer } from "../../api/types";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";

function centerFromPayload(p: unknown): [number, number] | null {
  const rec = p as
    { center?: [number, number]; geometry?: { type?: string; coordinates?: number[] } } | undefined;
  if (rec?.center) return rec.center;
  const g = rec?.geometry;
  if (g?.type === "Point" && Array.isArray(g.coordinates))
    return [g.coordinates[0], g.coordinates[1]];
  return null;
}

function geometryFromPayload(p: unknown): unknown | null {
  return (p as { geometry?: unknown } | undefined)?.geometry ?? null;
}

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: t("widgetMap.paletteLabel"),
    defaultProps: { dataSourceId: "", layers: [] },
    defaultSize: { w: 6, h: 6 },
    configSchema: [
      {
        name: "dataSourceId",
        type: "dataSource",
        label: t("widgetMap.dataSourceConfig"),
        default: "",
      },
    ],
    events: ["extentChanged", "itemSelected"],
    actions: ["flyTo", "highlight"],
    PropsPanel: ({ props, onChange, dataSources, theme }) => {
      const client = useItemClient();
      const dataSourceId = String(props.dataSourceId ?? "");
      const dataSource = dataSources.find((d) => d.id === dataSourceId);
      const datasetId = dataSource?.datasetId;
      // Résout le schéma de la collection liée — même source d'id que
      // runStatistics juste en dessous (dataSource.layer, patron
      // FormPropsPanel). Sert désormais aux DEUX sélecteurs : les champs
      // `attachment` pour le sélecteur « Pièces jointes » de PopupEditor
      // (revue finale de branche, I6), et tous les autres champs pour
      // `availableFields` de MapSymbologyEditor/PopupEditor (D11, SP-C6) —
      // un `availableFields={[]}` codé en dur empêchait jusqu'ici toute
      // configuration de symbologie/popup par champ depuis ce PropsPanel.
      const collectionId = dataSource?.layer ?? "";
      const schemaQuery = useQuery({
        queryKey: ["collection-schema", collectionId],
        queryFn: () => client.getCollectionSchema(collectionId),
        enabled: collectionId !== "",
      });
      const attachmentFields =
        schemaQuery.data?.fields.filter((f) => f.type === "attachment").map((f) => f.name) ?? [];
      const availableFields =
        schemaQuery.data?.fields.filter((f) => f.type !== "attachment").map((f) => f.name) ?? [];
      const center = props.center as [number, number] | undefined;
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect
            value={dataSourceId}
            dataSources={dataSources.filter((s) => s.type === "features")}
            onChange={(id) => onChange({ ...props, dataSourceId: id })}
          />
          <BasemapSelect
            value={String(props.basemapStyle ?? DEFAULT_STYLE)}
            onChange={(style) => onChange({ ...props, basemapStyle: style })}
          />
          <TerrainPanel
            value={(props.terrain as MapTerrainConfig | null) ?? null}
            onChange={(terrain) => onChange({ ...props, terrain })}
          />
          <CameraControls
            pitch={Number(props.cameraPitch ?? 0)}
            bearing={Number(props.cameraBearing ?? 0)}
            onChange={({ pitch, bearing }) =>
              onChange({ ...props, cameraPitch: pitch, cameraBearing: bearing })
            }
          />
          {/* D12 (SP-C6/Tâche 34) : la vue par défaut (centre/zoom) du
              Component runtime était un littéral en dur ([2.4, 46.6], zoom
              5) — aucune app ne pouvait cadrer sa carte par défaut ailleurs
              qu'en France métropolitaine. */}
          <div className="flex gap-2">
            <label className="flex flex-col gap-1 text-xs">
              {t("widgetMap.defaultCenterLngAria")}
              <input
                type="number"
                className="h-9 rounded-md border border-rule px-2 text-sm"
                value={Number(center?.[0] ?? 2.4)}
                onChange={(e) =>
                  onChange({
                    ...props,
                    center: [Number(e.target.value), center?.[1] ?? 46.6],
                  })
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              {t("widgetMap.defaultCenterLatAria")}
              <input
                type="number"
                className="h-9 rounded-md border border-rule px-2 text-sm"
                value={Number(center?.[1] ?? 46.6)}
                onChange={(e) =>
                  onChange({
                    ...props,
                    center: [center?.[0] ?? 2.4, Number(e.target.value)],
                  })
                }
              />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              {t("widgetMap.defaultZoomAria")}
              <input
                type="number"
                className="h-9 rounded-md border border-rule px-2 text-sm"
                value={Number(props.zoom ?? 5)}
                onChange={(e) => onChange({ ...props, zoom: Number(e.target.value) })}
              />
            </label>
          </div>
          <MapSymbologyEditor
            value={props.symbology as LayerSymbology | undefined}
            availableFields={availableFields}
            themeColors={theme?.colors}
            runStatistics={(query) =>
              client.queryDataSource({
                id: `map-domain-${datasetId}`,
                type: "statistics",
                service: "core",
                // `datasetId` se résout automatiquement côté queryDataSource
                // (types.ts:438) ; sans lui (source "features" branchée
                // directement sur une collection, cas valide et
                // sélectionnable — DataSourceSelect ne filtre que sur
                // `type === "features"`), c'est `dataSource.layer` qui porte
                // l'id de collection. Le hardcode précédent à "" produisait
                // un POST vers `/collections//aggregate` (I5 de la revue
                // finale SP-25) — la garde `enabled: Boolean(datasetId &&
                // field)` d'avant SP-25 avait été retirée sans repli.
                layer: dataSource?.layer ?? "",
                datasetId,
                query,
              })
            }
            // GAP-52 (4/4) : Jenks fonctionne désormais sur ce host via
            // ItemClient.sampleDataSourceField (résout collectionId depuis
            // dataSource.layer ou datasetId, symétrique de queryStatistics
            // ci-dessus) — `?.()` obligatoire (défaut n°5, brief Task 12) :
            // un ItemClient de test partiel n'implémente pas forcément cette
            // méthode.
            jenksAvailable={true}
            sampleField={(field, limit) =>
              client.sampleDataSourceField?.(
                { layer: dataSource?.layer ?? "", datasetId },
                field,
                limit,
              ) ?? Promise.reject(new Error(t("widgetMap.sampleFieldUnavailable")))
            }
            // `?.()` OBLIGATOIRE, pas cosmétique (défaut n° 5 de la brief
            // Task 12) : ce PropsPanel est rendu inconditionnellement, et
            // `renderPropsPanel` (mapWidget.test.tsx:126) le monte avec
            // `client={{} as unknown as ItemClient}` — un client entièrement
            // vide. Sans `?.`, `client.listMapIcons()` lève SYNCHRONIQUEMENT
            // dans le callback d'effet et fait échouer le rendu de tous les
            // tests passant par `renderPropsPanel` — le `.catch()` de
            // l'effet n'attrape rien, il n'y a pas encore de promesse.
            listCustomIcons={() => client.listMapIcons?.() ?? Promise.resolve([])}
            uploadCustomIcon={(file, title, category) =>
              // UN SEUL appel (D7) : plus de presign → PUT → POST. Le cœur
              // reçoit les octets, choisit la clé S3, assainit, puis écrit.
              client.uploadMapIcon(file, title, category)
            }
            deleteCustomIcon={(id) => client.deleteMapIcon(id)}
            onChange={(symbology) => onChange({ ...props, symbology })}
          />
          <PopupEditor
            value={props.popup as PopupConfig | undefined}
            availableFields={availableFields}
            attachmentFields={attachmentFields}
            onChange={(popup) => onChange({ ...props, popup })}
          />
          {/* LayersPanel embarque déjà son propre LayerPicker (source de
              recherche + formulaires tiles3d/deck/URL GeoJSON, cf.
              LayersPanel.tsx:421) pour ajouter à la liste qu'on lui passe —
              même patron que MapEditorPage.tsx:161. Un second <LayerPicker />
              autonome à côté produirait deux listes de sources identiques
              (constaté en test : deux boutons "Orthophoto (WMS)" dans la
              même liste). */}
          <div className="flex flex-col gap-2 border-t border-rule pt-2">
            <h3 className="text-xs font-semibold uppercase text-ink-2">
              {t("widgetMap.additionalLayersHeading")}
            </h3>
            <LayersPanel
              layers={(props.layers as MapLayer[] | undefined) ?? []}
              onChange={(layers) => onChange({ ...props, layers })}
            />
          </div>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const handle = useRef<MapViewHandle>(null);
      const client = useItemClient();
      // I1 (revue finale) : keyed sur l'id de source de données du widget,
      // pas sur l'URL brute — SP-A4 (auto-cadrage) et SP-A29 (contexte
      // d'emprise, `reactsToExtent`) bouclaient sinon : `onViewChange` →
      // `setExtent` → un dataset `reactsToExtent` change d'URL (bbox injecté)
      // → `lastFittedUrl` ne correspond plus → nouveau `fitBounds` → nouveau
      // `moveend` → boucle. L'identité du dataset lié à ce widget ne change
      // pas quand seule l'URL de fetch varie pour cette raison.
      const lastFittedDataSourceId = useRef<string | null>(null);
      // C1 (revue finale) : cf. commentaire jumeau sur MapEditorPage.tsx —
      // `onReady` (MapView.tsx) est le seul signal fiable que `handle.current`
      // est non-null, y compris pendant que le chunk lazy de MapView charge.
      const [mapReady, setMapReady] = useState(false);
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (payload) => {
        const center = centerFromPayload(payload);
        if (center) handle.current?.flyTo({ center, zoom: 12 });
      });
      useBusAction(ctx.bus, ctx.widgetId, "highlight", (payload) => {
        handle.current?.highlight(geometryFromPayload(payload));
      });
      const url = ctx.data?.url;
      const records = ctx.data?.records;
      const dataSourceId = String(props.dataSourceId ?? "");
      // Revue finale Vague C (point 6) : le cadrage automatique (D18, Vague
      // A) écrasait systématiquement le centre/zoom par défaut choisi par
      // l'auteur (D12, Task 34, ci-dessus dans PropsPanel) dès qu'un jeu de
      // données avec géométrie était lié — le cas normal. Un centre/zoom
      // n'est présent dans `props` QUE si l'auteur a explicitement modifié
      // au moins un des deux champs (les valeurs par défaut affichées dans
      // les <input> ci-dessus, [2.4, 46.6] et 5, ne sont écrites dans props
      // qu'au premier changement) — absent = jamais réglé, présent = intention
      // explicite de piloter la vue manuellement, qui doit primer sur
      // l'auto-cadrage.
      const authorSetView = props.center !== undefined || props.zoom !== undefined;
      useEffect(() => {
        if (authorSetView) return;
        if (!mapReady) return;
        if (!url || !records || records.length === 0) return;
        if (lastFittedDataSourceId.current === dataSourceId) return;
        const features: GeoJSON.Feature[] = records
          .filter((r) => r.geometry)
          .map((r) => ({
            type: "Feature",
            properties: {},
            geometry: r.geometry as GeoJSON.Geometry,
          }));
        const bbox = bboxFromFeatureCollection(features);
        if (!bbox) return;
        const view = handle.current;
        if (!view) return;
        lastFittedDataSourceId.current = dataSourceId;
        view.fitBounds(bbox);
      }, [url, records, mapReady, dataSourceId, authorSetView]);

      if (ctx.data?.error) return <p className="text-xs text-danger">{t("common.dataError")}</p>;

      const symbology = props.symbology as LayerSymbology | undefined;
      const geometryKind = detectGeometryKind(ctx.data?.records?.[0]?.geometry);
      // Le widget ne compile PLUS la peinture : il transmet la symbologie et
      // les couleurs de thème, et MapView compile — c'est le seul chemin qui
      // fait bénéficier les apps/dashboards du contour, des icônes, des
      // étiquettes et de l'opacité (SP-27). `renderAs` reste ici : c'est un
      // champ de la couche `feature`, et MapView en dérive sa géométrie.
      const renderAs = renderAsFor(geometryKind);
      const { encodings, colorDomain, sizeDomain, palette, stroke } = symbologyToPaintInputs(
        symbology,
        ctx.theme?.colors,
      );
      const legend = buildLegend(encodings, colorDomain, sizeDomain, geometryKind, palette, {
        stroke,
        icon: symbology?.icon,
      });

      const config: MapConfig = {
        basemap: { style: String(props.basemapStyle ?? DEFAULT_STYLE) },
        terrain: (props.terrain as MapTerrainConfig | null) ?? null,
        view: {
          center: (props.center as [number, number] | undefined) ?? [2.4, 46.6],
          zoom: Number(props.zoom ?? 5),
          pitch: Number(props.cameraPitch ?? 0),
          bearing: Number(props.cameraBearing ?? 0),
        },
        layers: [
          ...(url
            ? [
                {
                  id: `ds-${String(props.dataSourceId)}`,
                  title: t("widgetMap.layerTitle"),
                  visible: true,
                  kind: "feature" as const,
                  url,
                  renderAs,
                  ...(symbology ? { symbology } : {}),
                  popup: props.popup as PopupConfig | undefined,
                  collectionId: ctx.data?.collectionId,
                  pkColumn: ctx.data?.pkColumn,
                },
              ]
            : []),
          ...((props.layers as MapLayer[] | undefined) ?? []),
        ],
      };
      return (
        <div className="relative h-full">
          <ExplorerMenu
            datasetId={ctx.data?.datasetId}
            dataSourceId={String(props.dataSourceId ?? "")}
            resolvedSource={ctx.data?.resolvedSource}
            hasGeometry={ctx.data?.hasGeometry}
          />
          <Suspense
            fallback={<div className="text-xs text-ink-2">{t("widgetMap.loadingFallback")}</div>}
          >
            <MapView
              ref={handle}
              config={config}
              themeColors={ctx.theme?.colors}
              interactiveTools={ctx.mode !== "edit"}
              getAuthToken={client.getAuthToken}
              getCoreUrl={client.getCoreUrl}
              getShareLinkToken={client.getShareLinkToken}
              loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
              onReady={() => setMapReady(true)}
              onViewChange={(v) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "extentChanged", v);
                setExtent(v.bbox);
              }}
              onFeatureClick={(record) => {
                ctx.bus?.emit(ctx.widgetId ?? "", "itemSelected", record);
                const datasetId = ctx.data?.datasetId;
                const pkColumn = ctx.data?.pkColumn;
                if (datasetId && pkColumn)
                  setCrossFilter(
                    datasetId,
                    pkColumn,
                    String(record.id),
                    String(props.dataSourceId ?? ""),
                    record.geometry,
                  );
              }}
            />
          </Suspense>
          {legend && <MapSymbologyLegend legend={legend} />}
        </div>
      );
    },
  });
}
