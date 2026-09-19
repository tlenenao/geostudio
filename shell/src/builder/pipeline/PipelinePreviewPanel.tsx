// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from "react";
import { usePipelinePreview } from "../../api/hooks";
import type { PipelinePayload } from "../../api/types";
import { t } from "../../i18n";
import { Badge } from "../../ui/kit/Badge";
import { Button } from "../../ui/kit/Button";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

const PAGE_SIZE = 20;

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}/;

function compareCells(a: unknown, b: unknown): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

function formatCell(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString("fr-FR");
  if (typeof value === "string" && ISO_DATE_RE.test(value)) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed.toLocaleString("fr-FR");
  }
  return String(value);
}

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
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  // `previewQuery.data ?? []` allocates a new array identity on every render
  // while data is undefined (e.g. during a refetch), which would make a
  // `[rows]` dependency fire on unrelated renders instead of on actual data
  // changes — memoized so identity only changes when the underlying data
  // does (I6, final review).
  const rows = useMemo(() => previewQuery.data ?? [], [previewQuery.data]);

  // The preview re-executes on every draft edit, not just on a node switch
  // (Task 2) — a row selected before an edit must not silently point at "the
  // same index in the new result set", so this resets on the row set itself
  // changing, in addition to the node changing (I6, final review).
  useEffect(() => {
    setSelectedIndex(null);
  }, [nodeId, rows]);

  useEffect(() => {
    setPage(0);
  }, [rows, sortColumn, sortDirection]);

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

  const rowsWithIndex = rows.map((row, i) => ({ row, i }));
  const sortedRows =
    sortColumn === null
      ? rowsWithIndex
      : [...rowsWithIndex].sort((a, b) => {
          const cmp = compareCells(a.row[sortColumn], b.row[sortColumn]);
          return sortDirection === "asc" ? cmp : -cmp;
        });

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
                  <th
                    key={c}
                    className="cursor-pointer p-1 text-left"
                    onClick={() => {
                      if (sortColumn === c) {
                        setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
                      } else {
                        setSortColumn(c);
                        setSortDirection("asc");
                      }
                    }}
                    aria-sort={
                      sortColumn === c
                        ? sortDirection === "desc"
                          ? "descending"
                          : "ascending"
                        : "none"
                    }
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(({ row, i }) => (
                <tr
                  key={i}
                  onClick={() => setSelectedIndex(i)}
                  className={`cursor-pointer border-t border-rule ${i === selectedIndex ? "bg-sunken" : ""}`}
                >
                  {columns.map((c) =>
                    c === "geometry" ? (
                      <td key={c} className="p-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedIndex(i);
                            setView("map");
                          }}
                          className="text-accent underline"
                        >
                          {t("pipelinePreview.viewOnMap")}
                        </button>
                      </td>
                    ) : (
                      <td key={c} className="p-1">
                        {formatCell(row[c])}
                      </td>
                    ),
                  )}
                </tr>
              ))}
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
