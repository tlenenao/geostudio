// SPDX-License-Identifier: Apache-2.0
import { useState, type ChangeEvent } from "react";
import type { PrintLayoutConfig } from "../../api/types";
import { t } from "../../i18n";
import { Button } from "../../ui/kit/Button";
import { NativeSelect } from "../../ui/kit/NativeSelect";
import { Input } from "../../ui/kit/Input";
import { Textarea } from "../../ui/kit/Textarea";
import "../../i18n/domains/widgets";

// ~200 Ko : borne la config (le cœur plafonne le data URI à 400 000 car.).
const MAX_LOGO_BYTES = 200_000;

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

  const [logoError, setLogoError] = useState<string | null>(null);

  // Le logo est embarqué en data URI dans la config (jamais une URL : le
  // navigateur du worker d'export ne fait aucune requête sortante).
  function onLogoFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > MAX_LOGO_BYTES) {
      setLogoError(t("printLayout.logoTooLarge"));
      return;
    }
    setLogoError(null);
    const reader = new FileReader();
    reader.onload = () => patch({ logo: String(reader.result) });
    reader.readAsDataURL(file);
  }

  function patch(partial: Partial<PrintLayoutConfig>) {
    onChange({ ...current, ...partial });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-ink-2">{t("printLayout.heading")}</p>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.formatLabel")}
        <NativeSelect
          aria-label={t("printLayout.formatAria")}
          value={current.pageSize}
          onChange={(e) => patch({ pageSize: e.target.value as PrintLayoutConfig["pageSize"] })}
        >
          <option value="a4">A4</option>
          <option value="a3">A3</option>
        </NativeSelect>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.orientationLabel")}
        <NativeSelect
          aria-label={t("printLayout.orientationAria")}
          value={current.orientation}
          onChange={(e) =>
            patch({ orientation: e.target.value as PrintLayoutConfig["orientation"] })
          }
        >
          <option value="portrait">{t("printLayout.orientationPortrait")}</option>
          <option value="landscape">{t("printLayout.orientationLandscape")}</option>
        </NativeSelect>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.dpiLabel")}
        <NativeSelect
          value={String(current.dpi ?? 150)}
          onChange={(e) => patch({ dpi: Number(e.target.value) as PrintLayoutConfig["dpi"] })}
        >
          {[96, 150, 300, 600].map((d) => (
            <option key={d} value={String(d)}>
              {d} dpi
            </option>
          ))}
        </NativeSelect>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.titleLabel")}
        <Input
          type="text"
          value={current.title ?? ""}
          onChange={(e) => patch({ title: e.target.value || null })}
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={current.showLegend}
          onChange={(e) => patch({ showLegend: e.target.checked })}
        />
        {t("printLayout.legendLabel")}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={current.scaleBar ?? false}
          onChange={(e) => patch({ scaleBar: e.target.checked })}
        />
        {t("printLayout.scaleBarLabel")}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={current.northArrow ?? false}
          onChange={(e) => patch({ northArrow: e.target.checked })}
        />
        {t("printLayout.northArrowLabel")}
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.cartoucheLabel")}
        <Textarea
          value={current.cartouche ?? ""}
          onChange={(e) => patch({ cartouche: e.target.value || null })}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("printLayout.freeTextLabel")}
        <Textarea
          value={current.freeText ?? ""}
          onChange={(e) => patch({ freeText: e.target.value || null })}
        />
      </label>
      <div className="flex flex-col gap-1 text-sm">
        <label className="flex flex-col gap-1">
          {t("printLayout.logoLabel")}
          <input
            type="file"
            accept="image/png,image/jpeg,image/svg+xml,image/webp"
            onChange={onLogoFile}
          />
        </label>
        {current.logo && (
          <Button type="button" variant="outline" size="sm" onClick={() => patch({ logo: null })}>
            {t("printLayout.logoRemove")}
          </Button>
        )}
        {logoError && (
          <p role="alert" className="text-xs text-danger">
            {logoError}
          </p>
        )}
      </div>
    </div>
  );
}
