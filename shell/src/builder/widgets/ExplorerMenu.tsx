// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useExplorerEnabled, useOpenExplorer } from "../ExplorerContext";
import { useOptionalItemClient } from "../../api/ItemClientProvider";
import type { DataSource } from "../../api/types";

const AGGREGATE_FORMATS = ["csv", "xlsx"];
const ITEMS_FORMATS_WITH_GEOMETRY = ["csv", "xlsx", "geojson", "gpkg"];
const ITEMS_FORMATS_WITHOUT_GEOMETRY = ["csv", "xlsx"];

function formatsFor(source: DataSource, hasGeometry: boolean): string[] {
  if (source.type === "statistics") return AGGREGATE_FORMATS;
  return hasGeometry ? ITEMS_FORMATS_WITH_GEOMETRY : ITEMS_FORMATS_WITHOUT_GEOMETRY;
}

// requestBlob (itemClient.ts) throws a bare `Error("Request failed: <status> ...")`
// with no French-language mapping — parse the status back out of the message
// rather than changing itemClient's error-throwing shape.
function exportErrorMessage(err: unknown): string {
  const message = err instanceof Error ? err.message : "";
  const match = /^Request failed: (\d{3})\b/.exec(message);
  const status = match ? Number(match[1]) : null;
  if (status === 413) return "Trop d'entités : affinez vos filtres.";
  if (status === 403) return "Accès refusé.";
  return "Échec de l'export.";
}

export function ExplorerMenu({
  datasetId,
  dataSourceId,
  resolvedSource,
  hasGeometry,
}: {
  datasetId: string | undefined;
  dataSourceId: string;
  resolvedSource?: DataSource;
  hasGeometry?: boolean;
}) {
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const client = useOptionalItemClient();
  const [menuOpen, setMenuOpen] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  if (!enabled || !datasetId) return null;

  const formats = resolvedSource ? formatsFor(resolvedSource, Boolean(hasGeometry)) : [];

  // Closes the menu and clears any stale export error with it — the error
  // alert renders outside the menu's own subtree (see below), so it would
  // otherwise survive indefinitely once the menu closes.
  function closeMenu() {
    setMenuOpen(false);
    setExportError(null);
  }

  async function handleExport(format: string) {
    if (!resolvedSource || !client) return;
    // The menu closes immediately on click (its items, including this
    // button, unmount right away) — there is no pending/disabled state to
    // show on the button itself, so none is tracked here.
    closeMenu();
    try {
      const { blob, filename } = await client.exportDataSource(resolvedSource, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(exportErrorMessage(err));
    }
  }

  return (
    <div className="absolute right-1 top-1 z-10">
      <button
        type="button"
        aria-label="Explorer"
        className="rounded px-1 text-xs text-[var(--gs-color-muted)] hover:bg-[var(--gs-color-surface)]"
        onClick={() => (menuOpen ? closeMenu() : setMenuOpen(true))}
      >
        ⋮
      </button>
      {menuOpen && (
        <div className="absolute right-0 top-full mt-1 whitespace-nowrap rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-sm">
          <button
            type="button"
            aria-label="Voir les entités"
            className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
            onClick={() => {
              closeMenu();
              open({ datasetId, dataSourceId });
            }}
          >
            Voir les entités
          </button>
          {formats.map((format) => (
            <button
              key={format}
              type="button"
              aria-label={`Exporter en ${format.toUpperCase()}`}
              className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
              onClick={() => void handleExport(format)}
            >
              Exporter en {format.toUpperCase()}
            </button>
          ))}
        </div>
      )}
      {exportError && (
        <p
          role="alert"
          className="mt-1 whitespace-normal rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] px-2 py-1 text-xs text-red-600 shadow-sm"
        >
          {exportError}
        </p>
      )}
    </div>
  );
}
