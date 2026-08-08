// SPDX-License-Identifier: Apache-2.0
import type { PrintLayoutConfig } from "../../api/types";

const DEFAULTS: Required<Pick<PrintLayoutConfig, "pageSize" | "orientation" | "showLegend" | "showScaleBar" | "showNorthArrow">> = {
  pageSize: "a4", orientation: "portrait", showLegend: true, showScaleBar: true, showNorthArrow: false,
};

export function PrintLayoutPanel({
  value, onChange,
}: {
  value: PrintLayoutConfig | null;
  onChange: (next: PrintLayoutConfig | null) => void;
}) {
  const current = { ...DEFAULTS, ...(value ?? {}) };

  function patch(partial: Partial<PrintLayoutConfig>) {
    onChange({ ...current, ...partial });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Mise en page d&apos;impression</p>
      <label className="flex flex-col gap-1 text-sm">
        Format
        <select
          aria-label="Format"
          value={current.pageSize}
          onChange={(e) => patch({ pageSize: e.target.value as PrintLayoutConfig["pageSize"] })}
        >
          <option value="a4">A4</option>
          <option value="a3">A3</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Orientation
        <select
          aria-label="Orientation"
          value={current.orientation}
          onChange={(e) => patch({ orientation: e.target.value as PrintLayoutConfig["orientation"] })}
        >
          <option value="portrait">Portrait</option>
          <option value="landscape">Paysage</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <input
          aria-label="Titre"
          type="text"
          value={current.title ?? ""}
          onChange={(e) => patch({ title: e.target.value || null })}
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label="Légende"
          type="checkbox"
          checked={current.showLegend}
          onChange={(e) => patch({ showLegend: e.target.checked })}
        />
        Légende
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label="Barre d'échelle"
          type="checkbox"
          checked={current.showScaleBar}
          onChange={(e) => patch({ showScaleBar: e.target.checked })}
        />
        Barre d&apos;échelle
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label="Flèche nord"
          type="checkbox"
          checked={current.showNorthArrow}
          onChange={(e) => patch({ showNorthArrow: e.target.checked })}
        />
        Flèche nord
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Cartouche
        <textarea
          aria-label="Cartouche"
          value={current.cartouche ?? ""}
          onChange={(e) => patch({ cartouche: e.target.value || null })}
        />
      </label>
    </div>
  );
}
