// SPDX-License-Identifier: Apache-2.0
// REV-104 : lecteur temporel. Fait avancer une fenêtre [début, fin] à pas
// fixe sur la plage configurée et la pousse dans le contexte analytique
// global (useSetTimeRange), comme dateRangeFilter. Sans effet si
// config.interactions !== "auto". Bornes des props validées à l'écriture
// côté cœur (document_validation._time_player_errors).
import { useEffect, useState } from "react";
import { registerWidget } from "../registry";
import { useSetTimeRange } from "../AnalyticsContext";
import { t } from "../../i18n";

const DAY_MS = 86_400_000;
const SPEEDS = [0.5, 1, 2];
const NUMBER_FIELDS = [
  { key: "stepDays", label: "widgetTimePlayer.stepDays", min: 1, max: 3660 },
  { key: "windowDays", label: "widgetTimePlayer.windowDays", min: 1, max: 3660 },
  { key: "intervalMs", label: "widgetTimePlayer.intervalMs", min: 500, max: 10000 },
] as const;
const DATE_FIELDS = [
  { key: "from", label: "widgetTimePlayer.from" },
  { key: "to", label: "widgetTimePlayer.to" },
] as const;

/** Fenêtre n° `index` (dates ISO AAAA-MM-JJ, UTC), ou null une fois `to` dépassé. */
export function windowAt(
  from: string,
  to: string,
  stepDays: number,
  windowDays: number,
  index: number,
): { from: string; to: string } | null {
  const start = Date.parse(from) + index * stepDays * DAY_MS;
  const last = Date.parse(to);
  if (Number.isNaN(start) || Number.isNaN(last) || start > last) return null;
  const end = Math.min(start + (windowDays - 1) * DAY_MS, last);
  const iso = (ms: number) => new Date(ms).toISOString().slice(0, 10);
  return { from: iso(start), to: iso(end) };
}

export function registerTimePlayerWidget(): void {
  registerWidget({
    type: "timePlayer",
    label: t("widgetTimePlayer.paletteLabel"),
    defaultProps: { stepDays: 1, windowDays: 7, intervalMs: 1000 },
    defaultSize: { w: 6, h: 1 },
    configSchema: [
      { name: "stepDays", type: "number", label: t("widgetTimePlayer.stepDays"), default: 1 },
      { name: "windowDays", type: "number", label: t("widgetTimePlayer.windowDays"), default: 7 },
      {
        name: "intervalMs",
        type: "number",
        label: t("widgetTimePlayer.intervalMs"),
        default: 1000,
      },
    ],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        {DATE_FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1">
            {t(f.label)}
            <input
              type="date"
              className="h-9 rounded-md border border-rule px-2"
              value={String(props[f.key] ?? "")}
              onChange={(e) => onChange({ ...props, [f.key]: e.target.value || undefined })}
            />
          </label>
        ))}
        {NUMBER_FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1">
            {t(f.label)}
            <input
              type="number"
              min={f.min}
              max={f.max}
              step={1}
              className="h-9 rounded-md border border-rule px-2"
              value={props[f.key] === undefined ? "" : String(props[f.key])}
              onChange={(e) =>
                onChange({
                  ...props,
                  [f.key]: e.target.value === "" ? undefined : Number(e.target.value),
                })
              }
            />
          </label>
        ))}
      </div>
    ),
    Component: ({ props }) => {
      const setTimeRange = useSetTimeRange();
      const [index, setIndex] = useState(0);
      const [playing, setPlaying] = useState(false);
      const [speed, setSpeed] = useState(1);
      const from = String(props.from ?? "");
      const to = String(props.to ?? "");
      const stepDays = Number(props.stepDays) || 1;
      const windowDays = Number(props.windowDays) || 7;
      const intervalMs = Number(props.intervalMs) || 1000;

      // Un pas par intervalle ; nettoyé à la pause, au changement de vitesse
      // et au démontage.
      useEffect(() => {
        if (!playing) return;
        const timer = setInterval(() => setIndex((i) => i + 1), intervalMs / speed);
        return () => clearInterval(timer);
      }, [playing, intervalMs, speed]);

      // Pousse la fenêtre courante ; au-delà de la fin : arrêt et retour au début.
      useEffect(() => {
        if (!playing) return;
        const current = windowAt(from, to, stepDays, windowDays, index);
        if (current) {
          setTimeRange(current);
        } else {
          setPlaying(false);
          setIndex(0);
        }
      }, [playing, index, from, to, stepDays, windowDays, setTimeRange]);

      function play() {
        setPlaying(true);
      }
      function pause() {
        setPlaying(false);
      }

      if (!from || !to) {
        return (
          <p className="text-xs text-[var(--gs-color-text)]">
            {t("widgetTimePlayer.notConfigured")}
          </p>
        );
      }
      const shown = windowAt(from, to, stepDays, windowDays, index);
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm text-[var(--gs-color-text)]">
          <button
            type="button"
            className="h-9 rounded-md border border-[var(--gs-color-border)] px-3"
            onClick={() => (playing ? pause() : play())}
          >
            {playing ? t("widgetTimePlayer.pause") : t("widgetTimePlayer.play")}
          </button>
          <select
            aria-label={t("widgetTimePlayer.speed")}
            className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
            value={String(speed)}
            onChange={(e) => setSpeed(Number(e.target.value))}
          >
            {SPEEDS.map((s) => (
              <option key={s} value={String(s)}>
                {t("widgetTimePlayer.speedOption", { speed: s })}
              </option>
            ))}
          </select>
          {shown && <span>{t("analyticsContext.periodLabel", shown)}</span>}
        </div>
      );
    },
  });
}
