// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useExplorerEnabled, useOpenExplorer } from "../ExplorerContext";
import { useOptionalItemClient } from "../../api/ItemClientProvider";
import type { DataSource } from "../../api/types";
import { t } from "../../i18n";
import { saveExportedFile } from "../../api/saveExportedFile";
import { ApiError } from "../../api/ApiError";
import { usePanelTrigger } from "../../ui/kit/usePanelTrigger";

const AGGREGATE_FORMATS = ["csv", "xlsx"];
const ITEMS_FORMATS_WITH_GEOMETRY = ["csv", "xlsx", "geojson", "gpkg"];
const ITEMS_FORMATS_WITHOUT_GEOMETRY = ["csv", "xlsx"];

function formatsFor(source: DataSource, hasGeometry: boolean): string[] {
  if (source.type === "statistics") return AGGREGATE_FORMATS;
  return hasGeometry ? ITEMS_FORMATS_WITH_GEOMETRY : ITEMS_FORMATS_WITHOUT_GEOMETRY;
}

// SP-B5 : requestBlob (base.ts) jette désormais une ApiError typée
// (status/title/detail) plutôt qu'une Error générique — .status se lit
// directement. Le repli par expression régulière reste nécessaire pour les
// tests qui mockent exportDataSource() directement avec une Error brute
// ("Request failed: <status> ...") sans traverser requestBlob.
function exportErrorMessage(err: unknown): string {
  const status = err instanceof ApiError ? err.status : legacyStatus(err);
  if (status === 413) return t("explorerMenu.tooManyEntities");
  if (status === 403) return t("explorerMenu.accessDenied");
  return t("explorerMenu.exportFailed");
}

function legacyStatus(err: unknown): number | null {
  const message = err instanceof Error ? err.message : "";
  const match = /^Request failed: (\d{3})\b/.exec(message);
  return match ? Number(match[1]) : null;
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
  const menu = usePanelTrigger(menuOpen);
  const [exportError, setExportError] = useState<string | null>(null);
  // SP-60 : le sondage d'un export asynchrone s'arrête au démontage.
  const exportAbort = useRef<AbortController | null>(null);
  useEffect(() => () => exportAbort.current?.abort(), []);

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
    exportAbort.current?.abort();
    const ac = new AbortController();
    exportAbort.current = ac;
    try {
      const file = await client.exportDataSource(resolvedSource, format, ac.signal);
      saveExportedFile(file);
    } catch (err) {
      if (ac.signal.aborted) return;
      setExportError(exportErrorMessage(err));
    }
  }

  return (
    <div className="absolute right-1 top-1 z-10">
      <button
        type="button"
        aria-label={t("explorerMenu.trigger")}
        className="rounded px-1 text-xs text-[var(--gs-color-muted)] hover:bg-[var(--gs-color-surface)]"
        {...menu.triggerProps}
        onClick={() => (menuOpen ? closeMenu() : setMenuOpen(true))}
      >
        ⋮
      </button>
      {menuOpen && (
        <div
          {...menu.panelProps}
          className="absolute right-0 top-full mt-1 whitespace-nowrap rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] shadow-sm"
        >
          <button
            type="button"
            aria-label={t("explorerMenu.viewRecords")}
            className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
            onClick={() => {
              closeMenu();
              open({ datasetId, dataSourceId });
            }}
          >
            {t("explorerMenu.viewRecords")}
          </button>
          {formats.map((format) => (
            <button
              key={format}
              type="button"
              aria-label={t("explorerMenu.exportFormat", { format: format.toUpperCase() })}
              className="block w-full px-2 py-1 text-left text-xs text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
              onClick={() => void handleExport(format)}
            >
              {t("explorerMenu.exportFormat", { format: format.toUpperCase() })}
            </button>
          ))}
        </div>
      )}
      {exportError && (
        <p
          role="alert"
          className="mt-1 whitespace-normal rounded border border-[var(--gs-color-border)] bg-[var(--gs-color-background)] px-2 py-1 text-xs text-danger shadow-sm"
        >
          {exportError}
        </p>
      )}
    </div>
  );
}
