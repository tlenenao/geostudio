// SPDX-License-Identifier: Apache-2.0
import type { Theme } from "../api/types";
import {
  DEFAULT_THEME_COLORS,
  DEFAULT_FONT,
  DEFAULT_RADIUS,
  DEFAULT_SPACE,
  contrastRatio,
} from "./theme";
import { t } from "../i18n";
import { formatNumber } from "../lib/format";

const FONTS: [string, string][] = [
  [DEFAULT_FONT, t("themePanel.fontSystem")],
  ["Georgia, serif", t("themePanel.fontSerif")],
  ['"Courier New", monospace', t("themePanel.fontMonospace")],
];
const RADII: [string, string][] = [
  ["0px", t("themePanel.radiusSquare")],
  ["0.25rem", t("themePanel.radiusLight")],
  ["0.375rem", t("themePanel.radiusStandard")],
  ["0.75rem", t("themePanel.radiusRounded")],
  ["1rem", t("themePanel.radiusVeryRounded")],
];
const SPACES: [string, string][] = [
  ["0.25rem", t("themePanel.spaceCompact")],
  ["0.5rem", t("themePanel.spaceStandard")],
  ["1rem", t("themePanel.spaceAiry")],
];

const COLOR_FIELDS: [keyof NonNullable<Theme["colors"]>, string][] = [
  ["primary", t("themePanel.colorPrimary")],
  ["background", t("themePanel.colorBackground")],
  ["surface", t("themePanel.colorSurface")],
  ["text", t("themePanel.colorText")],
  ["muted", t("themePanel.colorMuted")],
  ["border", t("themePanel.colorBorder")],
];

// REV-284(e) : paires vérifiées contre le fond — le texte courant et la
// couleur atténuée (texte secondaire) ; seuil AA texte normal.
const MIN_CONTRAST = 4.5;
const CONTRAST_CHECKED: (keyof NonNullable<Theme["colors"]>)[] = ["text", "muted"];

export function ThemePanel({
  theme,
  onChange,
}: {
  theme: Theme;
  onChange: (theme: Theme) => void;
}) {
  function setColor(key: keyof NonNullable<Theme["colors"]>, value: string) {
    onChange({ ...theme, colors: { ...theme.colors, [key]: value } });
  }
  const colorOf = (key: keyof NonNullable<Theme["colors"]>) =>
    theme.colors?.[key] ?? DEFAULT_THEME_COLORS[key];
  const lowContrast = CONTRAST_CHECKED.flatMap((key) => {
    const ratio = contrastRatio(colorOf(key), colorOf("background"));
    if (ratio === null || ratio >= MIN_CONTRAST) return [];
    const label = COLOR_FIELDS.find(([k]) => k === key)?.[1] ?? key;
    return [{ key, label, ratio }];
  });
  return (
    <div className="flex flex-col gap-2 text-sm">
      {COLOR_FIELDS.map(([key, label]) => (
        <label key={key} className="flex items-center justify-between gap-2">
          {label}
          <input
            type="color"
            value={theme.colors?.[key] ?? DEFAULT_THEME_COLORS[key]}
            onChange={(e) => setColor(key, e.target.value)}
          />
        </label>
      ))}
      {lowContrast.map(({ key, label, ratio }) => (
        <p key={key} role="status" className="text-xs text-warn">
          {t("themePanel.lowContrast", { label, ratio: formatNumber(ratio, 1) })}
        </p>
      ))}
      <label className="flex flex-col gap-1">
        {t("themePanel.fontLabel")}
        <select
          className="h-9 rounded-md border border-rule px-2"
          value={theme.font ?? DEFAULT_FONT}
          onChange={(e) => onChange({ ...theme, font: e.target.value })}
        >
          {FONTS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        {t("themePanel.radiusFieldLabel")}
        <select
          className="h-9 rounded-md border border-rule px-2"
          value={theme.radius ?? DEFAULT_RADIUS}
          onChange={(e) => onChange({ ...theme, radius: e.target.value })}
        >
          {RADII.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        {t("themePanel.spaceLabel")}
        <select
          className="h-9 rounded-md border border-rule px-2"
          value={theme.space ?? DEFAULT_SPACE}
          onChange={(e) => onChange({ ...theme, space: e.target.value })}
        >
          {SPACES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
