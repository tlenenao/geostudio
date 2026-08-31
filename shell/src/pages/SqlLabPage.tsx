// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useItemClient } from "../api/ItemClientProvider";
import { appendSqlHistory, readSqlHistory, type SqlHistoryEntry } from "../lib/sqlLabHistory";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { EmptyState } from "../ui/kit/EmptyState";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

type SqlResult = { columns: string[]; rows: unknown[][]; truncated: boolean };

export function SqlLabPage() {
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

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="query"
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "query",
          label: "Requête",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">SQL Lab</h1>
              <label className="flex flex-col gap-1 text-sm text-ink">
                Requête SQL
                <textarea
                  aria-label="Requête SQL"
                  className="h-32 rounded-md border border-rule bg-surface p-2 font-mono text-xs text-ink"
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
                <p role="alert" className="text-sm text-danger">
                  {(run.error as Error).message}
                </p>
              )}
              {result && (
                <div>
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr>
                        {result.columns.map((col) => (
                          <th key={col} className="border-b border-rule p-1 text-ink">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, i) => (
                        <tr key={i}>
                          {row.map((cell, j) => (
                            <td key={j} className="border-b border-rule-2 p-1 text-ink">
                              {cell === null || cell === undefined ? "" : String(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {result.truncated && (
                    <p className="mt-1 text-xs text-ink-2">
                      Résultat tronqué aux {result.rows.length} premières lignes.
                    </p>
                  )}
                </div>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "history",
          label: "Historique",
          content: (
            <div className="flex flex-col gap-2 p-3">
              {history.length === 0 ? (
                <EmptyState title="Aucune requête exécutée pour l'instant." />
              ) : (
                <ul className="flex flex-col gap-1">
                  {history.map((entry, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs">
                      <span aria-hidden="true">{entry.status === "error" ? "✕" : "✓"}</span>
                      <button
                        type="button"
                        aria-label={`Recharger la requête : ${entry.sql}`}
                        className="text-left font-mono text-ink-2 hover:underline"
                        onClick={() => setSql(entry.sql)}
                      >
                        {entry.sql}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
