// SPDX-License-Identifier: Apache-2.0
import type { PrintLayoutConfig } from "../../api/types";

const DEFAULTS: Required<Pick<PrintLayoutConfig, "pageSize" | "orientation" | "showLegend">> = {
  pageSize: "a4",
  orientation: "portrait",
  showLegend: true,
};

export function PrintLayoutPanel({
  value,
  onChange,
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
      <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Mise en page d&apos;impression</p>
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
          onChange={(e) =>
            patch({ orientation: e.target.value as PrintLayoutConfig["orientation"] })
          }
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
      {/* showScaleBar/showNorthArrow controls removed (fix round, finding
          I4): they were authorable, validated, and round-tripped but never
          actually rendered anywhere in map or app export views — inert
          controls that silently did nothing. Real scale-bar/north-arrow
          rendering is out of scope for this fix round; the fields remain on
          PrintLayoutConfig/PrintLayout (core schema) for forward
          compatibility, just not exposed here until they do something. */}
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
