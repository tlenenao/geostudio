// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { usePipelinePreview } from "../../api/hooks";
import type { PipelinePayload } from "../../api/types";
import { t } from "../../i18n";
import { Badge } from "../../ui/kit/Badge";
import { Button } from "../../ui/kit/Button";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

const PAGE_SIZE = 20;

export function PipelinePreviewPanel({
  pipelineId,
  nodeId,
  draft,
  isDraftStale,
}: {
  pipelineId: string;
  nodeId: string | null;
  draft?: PipelinePayload;
  isDraftStale?: boolean;
}) {
  const previewQuery = usePipelinePreview(pipelineId, nodeId, draft);
  const [view, setView] = useState<"table" | "map">("table");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const rows = previewQuery.data ?? [];

  useEffect(() => {
    setSelectedIndex(null);
  }, [nodeId]);

  useEffect(() => {
    setPage(0);
  }, [rows]);

  if (nodeId === null) return null;
  if (previewQuery.isLoading) return <p role="status">{t("pipelinePreview.loading")}</p>;
  if (previewQuery.isError)
    return (
      <p role="alert" className="text-sm text-danger">
        {t("pipelinePreview.unavailable")}
      </p>
    );

  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  const hasGeometry = columns.includes("geometry");

  return (
    <div className="flex flex-col gap-2">
      {isDraftStale && (
        <div role="status">
          <Badge variant="warn">{t("pipelinePreview.stale")}</Badge>
        </div>
      )}
      {hasGeometry && (
        <div className="flex gap-1 text-xs">
          <button
            type="button"
            onClick={() => setView("table")}
            className={`rounded px-2 py-1 ${view === "table" ? "bg-sunken" : ""}`}
          >
            {t("pipelinePreview.tableView")}
          </button>
          <button
            type="button"
            onClick={() => setView("map")}
            className={`rounded px-2 py-1 ${view === "map" ? "bg-sunken" : ""}`}
          >
            {t("pipelinePreview.mapView")}
          </button>
        </div>
      )}
      {hasGeometry && view === "map" ? (
        <PipelinePreviewMap
          rows={rows}
          selectedIndex={selectedIndex}
          onSelectIndex={setSelectedIndex}
        />
      ) : (
        <>
          <table className="w-full text-xs">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} className="p-1 text-left">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((row, sliceIndex) => {
                const i = page * PAGE_SIZE + sliceIndex;
                return (
                  <tr
                    key={i}
                    onClick={() => setSelectedIndex(i)}
                    className={`cursor-pointer border-t border-rule ${i === selectedIndex ? "bg-sunken" : ""}`}
                  >
                    {columns.map((c) => (
                      <td key={c} className="p-1">
                        {String(row[c])}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length > 0 && (
            <div className="flex items-center gap-2 text-xs">
              <Button
                size="sm"
                variant="outline"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                {t("pipelinePreview.previousPage")}
              </Button>
              <span>
                {t("pipelinePreview.rowRange", {
                  from: page * PAGE_SIZE + 1,
                  to: Math.min((page + 1) * PAGE_SIZE, rows.length),
                  total: rows.length,
                })}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={(page + 1) * PAGE_SIZE >= rows.length}
                onClick={() => setPage((p) => p + 1)}
              >
                {t("pipelinePreview.nextPage")}
              </Button>
            </div>
          )}
        </>
      )}
      {selectedIndex !== null && rows[selectedIndex] && (
        <div className="rounded border border-rule p-2 text-xs">
          <p className="mb-1 font-medium text-ink-2">{t("pipelinePreview.featureAttributes")}</p>
          <dl className="grid grid-cols-2 gap-x-2 gap-y-1">
            {Object.entries(rows[selectedIndex])
              .filter(([c]) => c !== "geometry")
              .map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-2">{k}</dt>
                  <dd className="text-ink">{String(v)}</dd>
                </div>
              ))}
          </dl>
        </div>
      )}
    </div>
  );
}
