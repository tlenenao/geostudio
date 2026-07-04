import type { Theme } from "../api/types";
import { DEFAULT_THEME_COLORS, DEFAULT_FONT, DEFAULT_RADIUS, DEFAULT_SPACE } from "./theme";

const FONTS: [string, string][] = [
  ["system-ui, sans-serif", "Système"],
  ["Georgia, serif", "Serif"],
  ["\"Courier New\", monospace", "Monospace"],
];
const RADII: [string, string][] = [
  ["0px", "Carré"],
  ["0.25rem", "Léger"],
  ["0.375rem", "Standard"],
  ["0.75rem", "Arrondi"],
  ["1rem", "Très arrondi"],
];
const SPACES: [string, string][] = [
  ["0.25rem", "Compact"],
  ["0.5rem", "Standard"],
  ["1rem", "Aéré"],
];

const COLOR_FIELDS: [keyof NonNullable<Theme["colors"]>, string][] = [
  ["primary", "Couleur primaire"],
  ["background", "Couleur de fond"],
  ["surface", "Couleur de surface"],
  ["text", "Couleur du texte"],
  ["muted", "Couleur atténuée"],
  ["border", "Couleur de bordure"],
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
        Police
        <select
          aria-label="Police"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={theme.font ?? DEFAULT_FONT}
          onChange={(e) => onChange({ ...theme, font: e.target.value })}
        >
          {FONTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Arrondi
        <select
          aria-label="Arrondi"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={theme.radius ?? DEFAULT_RADIUS}
          onChange={(e) => onChange({ ...theme, radius: e.target.value })}
        >
          {RADII.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Espacement
        <select
          aria-label="Espacement"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={theme.space ?? DEFAULT_SPACE}
          onChange={(e) => onChange({ ...theme, space: e.target.value })}
        >
          {SPACES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
    </div>
  );
}
