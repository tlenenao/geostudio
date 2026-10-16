// SPDX-License-Identifier: Apache-2.0
import { useBasemaps } from "./useBasemaps";
import { t } from "../i18n";
import "../i18n/domains/map";

export function BasemapSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (style: string) => void;
}) {
  const basemaps = useBasemaps();
  return (
    <label className="flex flex-col gap-1 text-sm">
      {t("basemapSelect.label")}
      <select
        className="h-9 rounded-md border border-control bg-surface px-3 text-sm text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {basemaps.map((b) => (
          <option key={b.id} value={b.style}>
            {b.label}
          </option>
        ))}
      </select>
    </label>
  );
}
