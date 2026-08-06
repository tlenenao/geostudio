// SPDX-License-Identifier: Apache-2.0
import { usePipelinePreview } from "../../api/hooks";

export function PipelinePreviewPanel({ pipelineId, nodeId }: { pipelineId: string; nodeId: string | null }) {
  const previewQuery = usePipelinePreview(pipelineId, nodeId);

  if (nodeId === null) return null;
  if (previewQuery.isLoading) return <p role="status">Chargement de l'aperçu…</p>;
  if (previewQuery.isError) return <p role="alert" className="text-sm text-red-600">Aperçu indisponible.</p>;

  const rows = previewQuery.data ?? [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  return (
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
  );
}
