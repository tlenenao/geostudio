// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useMe } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import { appendSqlHistory, readSqlHistory, type SqlHistoryEntry } from "../lib/sqlLabHistory";
import { Button } from "../ui/button";

type SqlResult = { columns: string[]; rows: unknown[][]; truncated: boolean };

export function SqlLabPage() {
  const meQuery = useMe();
  const client = useItemClient();
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<SqlResult | null>(null);
  const [history, setHistory] = useState<SqlHistoryEntry[]>(() => readSqlHistory());

  const run = useMutation({
    mutationFn: (query: string) => client.runAnalyticsSql(query),
    onSuccess: (data, query) => {
      setResult(data);
      setHistory(
        appendSqlHistory({
          sql: query,
          executedAt: new Date().toISOString(),
          status: "ok",
          rowCount: data.rows.length,
        }),
      );
    },
    onError: (_error, query) => {
      setResult(null);
      setHistory(
        appendSqlHistory({ sql: query, executedAt: new Date().toISOString(), status: "error" }),
      );
    },
  });

  if (meQuery.isLoading) return <p role="status">Chargement…</p>;
  if (meQuery.data?.isAnalyst !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux analystes.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-bold">SQL Lab</h1>
      <label className="flex flex-col gap-1 text-sm">
        Requête SQL
        <textarea
          aria-label="Requête SQL"
          className="h-32 rounded-md border border-slate-300 p-2 font-mono text-xs"
          value={sql}
          onChange={(e) => setSql(e.target.value)}
        />
      </label>
      <Button
        size="sm"
        className="w-fit"
        disabled={!sql.trim() || run.isPending}
        onClick={() => run.mutate(sql)}
      >
        Exécuter
      </Button>
      {run.isError && (
        <p role="alert" className="text-sm text-red-600">
          {(run.error as Error).message}
        </p>
      )}
      {result && (
        <div>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                {result.columns.map((col) => (
                  <th key={col} className="border-b border-slate-200 p-1">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className="border-b border-slate-100 p-1">
                      {cell === null || cell === undefined ? "" : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {result.truncated && (
            <p className="mt-1 text-xs text-slate-500">
              Résultat tronqué aux {result.rows.length} premières lignes.
            </p>
          )}
        </div>
      )}
      {history.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Historique</p>
          <ul className="flex flex-col gap-1">
            {history.map((entry, i) => (
              <li key={i} className="flex items-center gap-2 text-xs">
                <span aria-hidden="true">{entry.status === "error" ? "✕" : "✓"}</span>
                <button
                  type="button"
                  aria-label={`Recharger la requête : ${entry.sql}`}
                  className="text-left font-mono text-slate-600 hover:underline"
                  onClick={() => setSql(entry.sql)}
                >
                  {entry.sql}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
