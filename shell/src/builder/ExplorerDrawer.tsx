// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCloseExplorer, useExplorerTarget } from "./ExplorerContext";
import { useAnalyticsContext } from "./AnalyticsContext";
import { useItemClient } from "../api/ItemClientProvider";
import { derivePatch } from "../lib/analyticsPatch";
import type { DataRecord, DataSource, MapConfig } from "../api/types";
import type { MapViewHandle } from "../map/MapView";
import { t } from "../i18n";

const MapView = lazy(() => import("../map/MapView").then((m) => ({ default: m.MapView })));
const DEFAULT_STYLE = "https://demotiles.maplibre.org/style.json";
const EXPLORER_LIMIT = 200;
const PAGE_SIZE = 20;

function columnsOf(records: DataRecord[]): string[] {
  return records[0] ? Object.keys(records[0].properties) : [];
}

export function ExplorerDrawer() {
  const target = useExplorerTarget();
  const close = useCloseExplorer();
  const analyticsCtx = useAnalyticsContext();
  const client = useItemClient();
  const mapHandle = useRef<MapViewHandle>(null);
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | number | null>(null);

  useEffect(() => {
    setPage(0);
    setSelectedId(null);
  }, [target?.datasetId]);

  useEffect(() => {
    if (!target) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [target, close]);

  const datasetQuery = useQuery({
    queryKey: ["dataset", target?.datasetId],
    queryFn: () => client.getDatasetConfig(target!.datasetId),
    enabled: Boolean(target),
  });
  const dataset = datasetQuery.data;

  const source: DataSource | null = target
    ? {
        id: "__explorer__",
        type: "features",
        service: "core",
        layer: "",
        datasetId: target.datasetId,
        query: { limit: EXPLORER_LIMIT },
      }
    : null;
  const patch =
    source && dataset ? derivePatch(source, analyticsCtx, { [target!.datasetId]: dataset }) : {};
  const merged: DataSource | null = source
    ? { ...source, query: { ...source.query, ...patch } }
    : null;

  const recordsQuery = useQuery({
    queryKey: ["datasource-explorer", target?.datasetId, merged?.query],
    queryFn: () => client.queryDataSource(merged!),
    enabled: Boolean(merged && dataset),
  });

  if (!target) return null;

  const records = recordsQuery.data ?? [];
  const columns = columnsOf(records);
  const pageCount = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const shown = records.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE);

  const mapConfig: MapConfig = {
    basemap: { style: DEFAULT_STYLE },
    view: { center: [2.4, 46.6], zoom: 5 },
    layers: merged
      ? [
          {
            id: "explorer",
            title: t("explorerDrawer.layerTitle"),
            visible: true,
            kind: "feature",
            url: client.featuresUrl(merged),
          },
        ]
      : [],
  };

  function selectRecord(r: DataRecord) {
    setSelectedId(r.id);
    mapHandle.current?.highlight(r.geometry ?? null);
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-lg">
      <div className="flex items-center justify-between border-b border-[var(--gs-color-border)] p-2">
        <h2 className="text-sm font-medium text-[var(--gs-color-text)]">
          {t("explorerDrawer.heading", {
            value: String(
              dataset
                ? dataset.source === "collection"
                  ? dataset.collectionId
                  : dataset.arcgisItemId
                : target.datasetId,
            ),
          })}
        </h2>
        <button
          type="button"
          aria-label={t("explorerDrawer.closeAria")}
          className="text-lg text-[var(--gs-color-muted)]"
          onClick={close}
        >
          ×
        </button>
      </div>
      <div className="h-48 shrink-0">
        <Suspense
          fallback={<div className="text-xs text-ink-2">{t("widgetMap.loadingFallback")}</div>}
        >
          <MapView
            ref={mapHandle}
            config={mapConfig}
            getAuthToken={client.getAuthToken}
            getCoreUrl={client.getCoreUrl}
            loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
          />
        </Suspense>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto p-2 text-xs">
        {(datasetQuery.isLoading || recordsQuery.isLoading) && (
          <p className="text-[var(--gs-color-muted)]">{t("common.loading")}</p>
        )}
        {!datasetQuery.isLoading &&
          !recordsQuery.isLoading &&
          (datasetQuery.isError || recordsQuery.isError) && (
            <p className="text-red-600">{t("common.dataError")}</p>
          )}
        {!datasetQuery.isLoading &&
          !recordsQuery.isLoading &&
          !datasetQuery.isError &&
          !recordsQuery.isError &&
          records.length === 0 && (
            <p className="text-[var(--gs-color-muted)]">{t("explorerDrawer.empty")}</p>
          )}
        {records.length >= EXPLORER_LIMIT && (
          <p className="mb-2 text-[var(--gs-color-muted)]">
            {t("explorerDrawer.limitMessage", { limit: EXPLORER_LIMIT })}
          </p>
        )}
        {shown.length > 0 && (
          <table className="w-full text-left">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} className="border-b border-[var(--gs-color-border)] p-1 font-medium">
                    {dataset?.columns[c]?.label ?? c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr
                  key={String(r.id)}
                  className={`cursor-pointer hover:bg-[var(--gs-color-surface)] ${selectedId === r.id ? "bg-[var(--gs-color-surface)]" : ""}`}
                  role="button"
                  tabIndex={0}
                  aria-label={t("explorerDrawer.viewRecordAria", {
                    value: String(r.properties[columns[0]] ?? r.id),
                  })}
                  onClick={() => selectRecord(r)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      if (e.key === " ") e.preventDefault();
                      selectRecord(r);
                    }
                  }}
                >
                  {columns.map((c) => (
                    <td key={c} className="border-b border-[var(--gs-color-border)] p-1">
                      {String(r.properties[c] ?? "")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {pageCount > 1 && (
          <div className="mt-auto flex items-center justify-between pt-2 text-[10px] text-[var(--gs-color-muted)]">
            <button
              type="button"
              aria-label={t("explorerDrawer.prevPageAria")}
              className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
              disabled={current === 0}
              onClick={() => setPage(current - 1)}
            >
              {t("explorerDrawer.previous")}
            </button>
            <span>{t("explorerDrawer.pageOf", { page: current + 1, totalPages: pageCount })}</span>
            <button
              type="button"
              aria-label={t("explorerDrawer.nextPageAria")}
              className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
              disabled={current >= pageCount - 1}
              onClick={() => setPage(current + 1)}
            >
              {t("explorerDrawer.next")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
