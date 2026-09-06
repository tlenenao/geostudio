// SPDX-License-Identifier: Apache-2.0
import type { Theme } from "../api/types";
import { DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";
import { t } from "../i18n";

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
  return (
    <div className="flex flex-col gap-2 text-sm">
      {COLOR_FIELDS.map(([key, label]) => (
        <label key={key} className="flex items-center justify-between gap-2">
          {label}
          <input
            type="color"
            aria-label={label}
            value={theme.colors?.[key] ?? DEFAULT_THEME_COLORS[key]}
            onChange={(e) => setColor(key, e.target.value)}
          />
        </label>
      ))}
      <label className="flex flex-col gap-1">
        {t("themePanel.fontLabel")}
        <select
          aria-label={t("themePanel.fontLabel")}
          className="h-9 rounded-md border border-slate-300 px-2"
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
          aria-label={t("themePanel.radiusFieldLabel")}
          className="h-9 rounded-md border border-slate-300 px-2"
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
          aria-label={t("themePanel.spaceLabel")}
          className="h-9 rounded-md border border-slate-300 px-2"
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
