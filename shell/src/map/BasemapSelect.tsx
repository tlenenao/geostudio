// SPDX-License-Identifier: Apache-2.0
import { BASEMAPS } from "./basemaps";
import { t } from "../i18n";

export function BasemapSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (style: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      {t("basemapSelect.label")}
      <select
        aria-label={t("basemapSelect.label")}
        className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {BASEMAPS.map((b) => (
          <option key={b.id} value={b.style}>
            {b.label}
          </option>
        ))}
      </select>
    </label>
  );
}
