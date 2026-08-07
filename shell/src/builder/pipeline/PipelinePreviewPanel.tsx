// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { usePipelinePreview } from "../../api/hooks";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

export function PipelinePreviewPanel({ pipelineId, nodeId }: { pipelineId: string; nodeId: string | null }) {
  const previewQuery = usePipelinePreview(pipelineId, nodeId);
  const [view, setView] = useState<"table" | "map">("table");

  if (nodeId === null) return null;
  if (previewQuery.isLoading) return <p role="status">Chargement de l'aperçu…</p>;
  if (previewQuery.isError) return <p role="alert" className="text-sm text-red-600">Aperçu indisponible.</p>;

  const rows = previewQuery.data ?? [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  const hasGeometry = columns.includes("geometry");

  return (
    <div className="flex flex-col gap-2">
      {hasGeometry && (
        <div className="flex gap-1 text-xs">
          <button
            type="button" onClick={() => setView("table")}
            className={`rounded px-2 py-1 ${view === "table" ? "bg-slate-200" : ""}`}
          >
            Tableau
          </button>
          <button
            type="button" onClick={() => setView("map")}
            className={`rounded px-2 py-1 ${view === "map" ? "bg-slate-200" : ""}`}
          >
            Carte
          </button>
        </div>
      )}
      {hasGeometry && view === "map" ? (
        <PipelinePreviewMap rows={rows} />
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr>{columns.map((c) => <th key={c} className="p-1 text-left">{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-slate-200">
                {columns.map((c) => <td key={c} className="p-1">{String(row[c])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
