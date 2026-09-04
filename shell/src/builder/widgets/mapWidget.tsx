// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useRef } from "react";
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
import type { LayerSymbology, LegendSpec } from "./mapSymbology";
import type { MapConfig, PopupConfig } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { ExplorerMenu } from "./ExplorerMenu";
import { PopupEditor } from "../../map/PopupEditor";
import { MapSymbologyEditor } from "../../map/MapSymbologyEditor";

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

function MapSymbologyLegend({ legend }: { legend: LegendSpec }) {
  return (
    <div className="absolute bottom-2 right-2 z-10 flex flex-col gap-2 rounded-md bg-white/90 p-2 text-xs shadow">
      {legend.color?.kind === "categorical" && (
        <ul>
          {legend.color.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: e.color }}
              />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {legend.color?.kind === "classed" && (
        <ul>
          {legend.color.classes.map((c, i) => (
            <li key={i} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: c.color }}
              />
              {c.from.toFixed(1)} – {c.to.toFixed(1)}
            </li>
          ))}
        </ul>
      )}
      {legend.color?.kind === "numeric" && (
        <div>
          <div
            className="h-2 w-24 rounded"
            style={{
              background: `linear-gradient(to right, ${legend.color.colorLow}, ${legend.color.colorHigh})`,
            }}
          />
          <span>
            {legend.color.min} – {legend.color.max}
          </span>
        </div>
      )}
      {legend.size && (
        <div className="flex items-end gap-2">
          <span
            className="rounded-full bg-slate-500"
            style={{ width: legend.size.radiusMin, height: legend.size.radiusMin }}
          />
          <span
            className="rounded-full bg-slate-500"
            style={{ width: legend.size.radiusMax, height: legend.size.radiusMax }}
          />
          <span>
            {legend.size.min} – {legend.size.max}
          </span>
        </div>
      )}
      {legend.stroke?.kind === "categorical" && (
        <ul aria-label="Contour">
          {legend.stroke.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm border-2"
                style={{ borderColor: e.color }}
              />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {/* Fix I2 de la revue finale SP-27 : un contour classé/continu se
          compile correctement (buildMapPaint, expression step/interpolate
          sur fill-outline-color) depuis que Task 5 a rendu le sélecteur de
          couleur de contour symétrique du remplissage, mais la légende ne
          savait décrire que le cas catégoriel — miroir exact des blocs
          legend.color juste au-dessus. */}
      {legend.stroke?.kind === "classed" && (
        <ul aria-label="Contour">
          {legend.stroke.classes.map((c, i) => (
            <li key={i} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm border-2"
                style={{ borderColor: c.color }}
              />
              {c.from.toFixed(1)} – {c.to.toFixed(1)}
            </li>
          ))}
        </ul>
      )}
      {legend.stroke?.kind === "numeric" && (
        <div aria-label="Contour">
          <div
            className="h-2 w-24 rounded border-2"
            style={{
              background: `linear-gradient(to right, ${legend.stroke.colorLow}, ${legend.stroke.colorHigh})`,
            }}
          />
          <span>
            {legend.stroke.min} – {legend.stroke.max}
          </span>
        </div>
      )}
      {legend.icon && (
        <ul aria-label="Icônes">
          {legend.icon.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span aria-hidden="true" className="text-base">
                ◈
              </span>
              {e.value}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function registerMapWidget(): void {
  registerWidget({
    type: "map",
    label: "Carte",
    defaultProps: { dataSourceId: "" },
    defaultSize: { w: 6, h: 6 },
    configSchema: [
      { name: "dataSourceId", type: "dataSource", label: "Source de données", default: "" },
    ],
    events: ["extentChanged", "itemSelected"],
    actions: ["flyTo", "highlight"],
    PropsPanel: ({ props, onChange, dataSources, theme }) => {
      const client = useItemClient();
      const dataSourceId = String(props.dataSourceId ?? "");
      const dataSource = dataSources.find((d) => d.id === dataSourceId);
      const datasetId = dataSource?.datasetId;
      // Résout le schéma pour offrir les champs `attachment` déclarés sur la
      // collection au sélecteur « Pièces jointes » de PopupEditor (revue
      // finale de branche, I6) — même source d'id de collection que
      // runStatistics juste en dessous (dataSource.layer, patron
      // FormPropsPanel). N'étend PAS availableFields de MapSymbologyEditor
      // (toujours [], limitation documentée et volontairement non élargie
      // ici, cf. commentaire jenksAvailable/sampleField ci-dessous) — hors
      // périmètre de ce correctif.
      const collectionId = dataSource?.layer ?? "";
      const schemaQuery = useQuery({
        queryKey: ["collection-schema", collectionId],
        queryFn: () => client.getCollectionSchema(collectionId),
        enabled: collectionId !== "",
      });
      const attachmentFields =
        schemaQuery.data?.fields.filter((f) => f.type === "attachment").map((f) => f.name) ?? [];
      return (
        <div className="flex flex-col gap-2 text-sm">
          <DataSourceSelect
            value={dataSourceId}
            dataSources={dataSources.filter((s) => s.type === "features")}
            onChange={(id) => onChange({ ...props, dataSourceId: id })}
          />
          <MapSymbologyEditor
            value={props.symbology as LayerSymbology | undefined}
            availableFields={[]} // PropsPanel has no schema (registry.ts) — same PopupEditor precedent
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
            // Jenks a besoin d'un collectionId résolu pour échantillonner un
            // champ ; ce host n'en a pas (portée volontairement non
            // élargie ici, cf. brief I5) — l'option est masquée plutôt que
            // de laisser l'auteur la choisir puis échouer au clic.
            jenksAvailable={false}
            sampleField={async () => {
              throw new Error(
                "Jenks sur le widget carte nécessite un collectionId résolu — non câblé",
              );
            }}
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
            availableFields={[]}
            attachmentFields={attachmentFields}
            onChange={(popup) => onChange({ ...props, popup })}
          />
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const handle = useRef<MapViewHandle>(null);
      const client = useItemClient();
      const setExtent = useSetExtent();
      const setCrossFilter = useSetCrossFilter();
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (payload) => {
        const center = centerFromPayload(payload);
        if (center) handle.current?.flyTo({ center, zoom: 12 });
      });
      useBusAction(ctx.bus, ctx.widgetId, "highlight", (payload) => {
        handle.current?.highlight(geometryFromPayload(payload));
      });

      if (ctx.data?.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      const url = ctx.data?.url;

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
        basemap: { style: DEFAULT_STYLE },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: url
          ? [
              {
                id: `ds-${String(props.dataSourceId)}`,
                title: "Données",
                visible: true,
                kind: "feature",
                url,
                renderAs,
                ...(symbology ? { symbology } : {}),
                popup: props.popup as PopupConfig | undefined,
                collectionId: ctx.data?.collectionId,
                pkColumn: ctx.data?.pkColumn,
              },
            ]
          : [],
      };
      return (
        <div className="relative h-full">
          <ExplorerMenu
            datasetId={ctx.data?.datasetId}
            dataSourceId={String(props.dataSourceId ?? "")}
            resolvedSource={ctx.data?.resolvedSource}
            hasGeometry={ctx.data?.hasGeometry}
          />
          <Suspense fallback={<div className="text-xs text-slate-400">Carte…</div>}>
            <MapView
              ref={handle}
              config={config}
              themeColors={ctx.theme?.colors}
              interactiveTools={ctx.mode !== "edit"}
              getAuthToken={client.getAuthToken}
              getCoreUrl={client.getCoreUrl}
              loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
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
