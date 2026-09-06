// SPDX-License-Identifier: Apache-2.0
import type { PrintLayoutConfig } from "../../api/types";
import { t } from "../../i18n";

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
      <p className="mb-1 mt-3 text-xs font-medium text-ink-2">{t("printLayout.heading")}</p>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.formatLabel")}
        <select
          aria-label={t("printLayout.formatAria")}
          value={current.pageSize}
          onChange={(e) => patch({ pageSize: e.target.value as PrintLayoutConfig["pageSize"] })}
        >
          <option value="a4">A4</option>
          <option value="a3">A3</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.orientationLabel")}
        <select
          aria-label={t("printLayout.orientationAria")}
          value={current.orientation}
          onChange={(e) =>
            patch({ orientation: e.target.value as PrintLayoutConfig["orientation"] })
          }
        >
          <option value="portrait">{t("printLayout.orientationPortrait")}</option>
          <option value="landscape">{t("printLayout.orientationLandscape")}</option>
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.titleLabel")}
        <input
          aria-label={t("printLayout.titleAria")}
          type="text"
          value={current.title ?? ""}
          onChange={(e) => patch({ title: e.target.value || null })}
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label={t("printLayout.legendAria")}
          type="checkbox"
          checked={current.showLegend}
          onChange={(e) => patch({ showLegend: e.target.checked })}
        />
        {t("printLayout.legendLabel")}
      </label>
      {/* showScaleBar/showNorthArrow (fix round, finding I4) were removed
          entirely from PrintLayoutConfig/PrintLayout (core schema, REV-128):
          they were authorable, validated, and round-tripped but never
          actually rendered anywhere in map or app export views — inert
          fields that silently did nothing. Real scale-bar/north-arrow
          rendering remains out of scope; if it's ever built, it should add
          new fields rather than resurrect these. */}
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.cartoucheLabel")}
        <textarea
          aria-label={t("printLayout.cartoucheAria")}
          value={current.cartouche ?? ""}
          onChange={(e) => patch({ cartouche: e.target.value || null })}
        />
      </label>
    </div>
  );
}
