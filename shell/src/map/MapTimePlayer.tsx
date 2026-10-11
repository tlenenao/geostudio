// SPDX-License-Identifier: Apache-2.0
// ARC-09b : lecteur temps de l'éditeur de carte. Réutilise `windowAt` du widget
// `timePlayer` (REV-104) ; l'état est persisté dans `MapConfig.timePlayer`
// (l'index n'est écrit qu'à la pause, pas à chaque pas). La fenêtre courante
// est poussée via `onRange` : l'hôte l'applique aux couches `timeField`
// (filtre `datetime` d'ARC-02 pour les `feature`, setFilter pour les `vector`).
import { useEffect, useState } from "react";
import type { MapTimePlayerConfig } from "../api/types";
import { windowAt } from "../builder/widgets/timePlayer";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";
import "../i18n/domains/map";
import "../i18n/domains/widgets";

type Range = { from: string; to: string };

export function MapTimePlayer({
  value,
  onChange,
  onRange,
}: {
  value: MapTimePlayerConfig | null;
  onChange: (next: MapTimePlayerConfig | null) => void;
  onRange: (range: Range | null) => void;
}) {
  const [index, setIndex] = useState(value?.windowIndex ?? 0);
  const [playing, setPlaying] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const win = value
    ? windowAt(value.start, value.end, value.stepDays, value.windowDays, index)
    : null;
  const from = win?.from;
  const to = win?.to;
  useEffect(() => {
    onRange(from && to ? { from, to } : null);
  }, [from, to, onRange]);

  useEffect(() => {
    if (!playing || !value) return;
    const timer = setInterval(() => setIndex((i) => i + 1), value.intervalMs);
    return () => clearInterval(timer);
  }, [playing, value]);

  // Fin de plage : arrêt et retour au début (comme le widget).
  useEffect(() => {
    if (value && !win) {
      setPlaying(false);
      setIndex(0);
    }
  }, [value, win]);

  function create(s: string, e: string) {
    if (s && e) {
      onChange({ start: s, end: e, stepDays: 1, windowDays: 7, intervalMs: 1000, windowIndex: 0 });
      setIndex(0);
    }
  }

  if (!value) {
    return (
      <div className="flex flex-wrap items-end gap-2 text-sm" aria-label={t("mapTimePlayer.title")}>
        <label className="flex flex-col gap-1">
          {t("widgetTimePlayer.from")}
          <input
            type="date"
            className="h-9 rounded-md border border-rule px-2"
            value={start}
            onChange={(ev) => {
              setStart(ev.target.value);
              create(ev.target.value, end);
            }}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("widgetTimePlayer.to")}
          <input
            type="date"
            className="h-9 rounded-md border border-rule px-2"
            value={end}
            onChange={(ev) => {
              setEnd(ev.target.value);
              create(start, ev.target.value);
            }}
          />
        </label>
      </div>
    );
  }

  function play() {
    setPlaying(true);
  }
  function pause() {
    if (value) onChange({ ...value, windowIndex: index });
    setPlaying(false);
  }

  return (
    <div
      className="flex flex-wrap items-center gap-2 text-sm"
      aria-label={t("mapTimePlayer.title")}
    >
      <Button variant="outline" onClick={() => (playing ? pause() : play())}>
        {playing ? t("widgetTimePlayer.pause") : t("widgetTimePlayer.play")}
      </Button>
      {win && <span>{t("analyticsContext.periodLabel", win)}</span>}
      <Button
        variant="ghost"
        onClick={() => {
          setPlaying(false);
          onChange(null);
        }}
      >
        {t("mapTimePlayer.remove")}
      </Button>
    </div>
  );
}
