// SPDX-License-Identifier: Apache-2.0
// ARC-34 : widget « Directions » — itinéraire entre deux points (adresse ou « latitude, longitude »)
// via POST /v1/routing/route (Valhalla derrière le cœur : privilège analytics.view, 503 lisible si le
// service est absent). Émet `routeComputed` {distanceKm, durationS, geometry} que l'auteur câble à
// un autre widget. Absent des exports statique/autoporté (pas de routage cœur).
import { useState } from "react";
import { registerWidget } from "../registry";
import { useItemClient } from "../../api/ItemClientProvider";
import type { ItemClient, RouteCosting, RoutePoint, RouteResult } from "../../api/types";
import { Button } from "../../ui/kit/Button";
import { Input } from "../../ui/kit/Input";
import { NativeSelect } from "../../ui/kit/NativeSelect";
import { Field } from "../../ui/kit/Field";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";

const COSTING_LABELS: Record<RouteCosting, () => string> = {
  auto: () => t("widgetDirections.costingAuto"),
  bicycle: () => t("widgetDirections.costingBicycle"),
  pedestrian: () => t("widgetDirections.costingPedestrian"),
  truck: () => t("widgetDirections.costingTruck"),
  bus: () => t("widgetDirections.costingBus"),
  motor_scooter: () => t("widgetDirections.costingMotorScooter"),
};
const COSTINGS = Object.keys(COSTING_LABELS) as RouteCosting[];
const MAX_MANEUVERS = 50;
const COORDS = /^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$/;

// « 45.26, 1.77 » = latitude, longitude ; sinon la saisie est une adresse géocodée par le cœur.
async function resolvePoint(client: ItemClient, text: string): Promise<RoutePoint | null> {
  const m = COORDS.exec(text);
  if (m) {
    const lat = Number(m[1]);
    const lon = Number(m[2]);
    return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lon, lat } : null;
  }
  const [hit] = await client.geocode(text.trim(), 1);
  return hit ? { lon: hit.lon, lat: hit.lat } : null;
}

function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  return minutes < 60
    ? t("widgetDirections.minutes", { count: String(minutes) })
    : t("widgetDirections.hoursMinutes", {
        hours: String(Math.floor(minutes / 60)),
        minutes: String(minutes % 60),
      });
}

function DirectionsPanel({ onRoute }: { onRoute: (route: RouteResult) => void }) {
  const client = useItemClient();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [costing, setCosting] = useState<RouteCosting>("auto");
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const [a, b] = await Promise.all([resolvePoint(client, from), resolvePoint(client, to)]);
      if (!a || !b) {
        setRoute(null);
        setError(t("widgetDirections.notFound"));
        return;
      }
      const result = await client.computeRoute([a, b], costing);
      setRoute(result);
      onRoute(result);
    } catch (e) {
      setRoute(null);
      setError(e instanceof Error ? e.message : t("widgetDirections.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="flex flex-col gap-2 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        void run();
      }}
    >
      <Field label={t("widgetDirections.from")} htmlFor="directions-from">
        <Input id="directions-from" value={from} onChange={(e) => setFrom(e.target.value)} />
      </Field>
      <Field label={t("widgetDirections.to")} htmlFor="directions-to">
        <Input id="directions-to" value={to} onChange={(e) => setTo(e.target.value)} />
      </Field>
      <Field label={t("widgetDirections.mode")} htmlFor="directions-mode">
        <NativeSelect
          id="directions-mode"
          value={costing}
          onChange={(e) => setCosting(e.target.value as RouteCosting)}
        >
          {COSTINGS.map((c) => (
            <option key={c} value={c}>
              {COSTING_LABELS[c]()}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={busy || from.trim() === "" || to.trim() === ""}>
          {t("widgetDirections.run")}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
      {route && (
        <div role="status" className="flex flex-col gap-1">
          <p>
            {t("widgetDirections.summary", {
              distance: route.distance_km.toFixed(1).replace(".", ","),
              duration: formatDuration(route.duration_s),
            })}
          </p>
          <ol className="list-decimal pl-5 text-xs">
            {route.legs
              .flatMap((leg) => leg.maneuvers)
              .slice(0, MAX_MANEUVERS)
              .map((m, i) => (
                <li key={i}>{m.instruction}</li>
              ))}
          </ol>
        </div>
      )}
    </form>
  );
}

export function registerDirectionsWidget(): void {
  registerWidget({
    type: "directions",
    label: t("widgetDirections.paletteLabel"),
    defaultProps: {},
    defaultSize: { w: 4, h: 6 },
    events: ["routeComputed"],
    actions: [],
    configSchema: [],
    PropsPanel: () => <p className="text-xs">{t("widgetDirections.propsHint")}</p>,
    Component: ({ ctx }) =>
      // En édition, aucun appel réseau : simple repère visuel.
      ctx.mode === "edit" ? (
        <p className="text-sm text-[var(--gs-color-text)]">{t("widgetDirections.editHint")}</p>
      ) : (
        <DirectionsPanel
          onRoute={(route) =>
            ctx.bus?.emit(ctx.widgetId ?? "", "routeComputed", {
              distanceKm: route.distance_km,
              durationS: route.duration_s,
              geometry: route.geometry,
            })
          }
        />
      ),
  });
}
