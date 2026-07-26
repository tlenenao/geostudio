// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useExplorerEnabled, useOpenExplorer } from "../ExplorerContext";

export function ExplorerMenu({
  datasetId, dataSourceId,
}: {
  datasetId: string | undefined;
  dataSourceId: string;
}) {
  const enabled = useExplorerEnabled();
  const open = useOpenExplorer();
  const [menuOpen, setMenuOpen] = useState(false);

  if (!enabled || !datasetId) return null;

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
        </div>
      )}
    </div>
  );
}
