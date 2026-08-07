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

export function ExplorerMenu({
  datasetId, dataSourceId, resolvedSource, hasGeometry,
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
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);

  if (!enabled || !datasetId) return null;

  const formats = resolvedSource ? formatsFor(resolvedSource, Boolean(hasGeometry)) : [];

  async function handleExport(format: string) {
    if (!resolvedSource || !client) return;
    setMenuOpen(false);
    setExportError(null);
    setExportingFormat(format);
    try {
      const { blob, filename } = await client.exportDataSource(resolvedSource, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Échec de l'export.");
    } finally {
      setExportingFormat(null);
    }
  }

  return (
    <div className="absolute right-1 top-1 z-10">
      <button
        type="button"
        aria-label="Explorer"
        className="rounded px-1 text-xs text-[var(--gs-color-muted)] hover:bg-[var(--gs-color-surface)]"
        onClick={() => setMenuOpen((v) => !v)}
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
              setMenuOpen(false);
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
              disabled={exportingFormat === format}
              className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)] disabled:opacity-50"
              onClick={() => handleExport(format)}
            >
              Exporter en {format.toUpperCase()}
            </button>
          ))}
        </div>
      )}
      {exportError && (
        <p role="alert" className="mt-1 whitespace-normal rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] px-2 py-1 text-xs text-red-600 shadow-sm">
          {exportError}
        </p>
      )}
    </div>
  );
}
