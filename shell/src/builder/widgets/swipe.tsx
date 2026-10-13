// SPDX-License-Identifier: Apache-2.0
// ARC-26 : widget Swipe (comparaison avant/après). Deux cartes superposées,
// la droite est révélée par un curseur ; la caméra de l'une suit l'autre.
// Gauche = fond `leftStyle` seul ; droite = fond `rightStyle` + `layers`.
import { lazy, Suspense, useRef, useState } from "react";
import { registerWidget } from "../registry";
import { useItemClient } from "../../api/ItemClientProvider";
import type { MapConfig, MapLayer } from "../../api/types";
import type { MapViewHandle } from "../../map/MapView";
import { BASEMAPS } from "../../map/basemaps";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";

const MapView = lazy(() => import("../../map/MapView").then((m) => ({ default: m.MapView })));

type View = { center: [number, number]; zoom: number; pitch: number; bearing: number };
const EPS = 1e-6;
const same = (a: View, b: View) =>
  Math.abs(a.center[0] - b.center[0]) < EPS &&
  Math.abs(a.center[1] - b.center[1]) < EPS &&
  Math.abs(a.zoom - b.zoom) < EPS &&
  Math.abs(a.pitch - b.pitch) < EPS &&
  Math.abs(a.bearing - b.bearing) < EPS;

const inputCls = "h-9 rounded-md border border-control bg-surface px-2 text-ink";

export function registerSwipeWidget(): void {
  registerWidget({
    type: "swipe",
    label: t("widgetSwipe.paletteLabel"),
    defaultProps: { leftStyle: BASEMAPS[1].style, rightStyle: BASEMAPS[2].style, layers: [] },
    defaultSize: { w: 8, h: 6 },
    configSchema: [
      { name: "leftStyle", type: "string", label: t("widgetSwipe.leftConfig"), default: "" },
      { name: "rightStyle", type: "string", label: t("widgetSwipe.rightConfig"), default: "" },
    ],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        {(["leftStyle", "rightStyle"] as const).map((key) => (
          <label key={key} className="flex flex-col gap-1">
            {t(key === "leftStyle" ? "widgetSwipe.leftConfig" : "widgetSwipe.rightConfig")}
            <select
              className={inputCls}
              value={String(props[key] ?? "")}
              onChange={(e) => onChange({ ...props, [key]: e.target.value })}
            >
              {BASEMAPS.map((b) => (
                <option key={b.id} value={b.style}>
                  {b.label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
    ),
    Component: ({ props, ctx }) => {
      const client = useItemClient();
      const [pos, setPos] = useState(50);
      const left = useRef<MapViewHandle>(null);
      const right = useRef<MapViewHandle>(null);
      const lastView = useRef<View | null>(null);

      const base: Omit<MapConfig, "basemap" | "layers"> = {
        view: {
          center: (props.center as [number, number] | undefined) ?? [2.4, 46.6],
          zoom: Number(props.zoom ?? 5),
          pitch: 0,
          bearing: 0,
        },
      };
      const leftConfig: MapConfig = {
        ...base,
        basemap: { style: String(props.leftStyle ?? BASEMAPS[1].style) },
        layers: [],
      };
      const rightConfig: MapConfig = {
        ...base,
        basemap: { style: String(props.rightStyle ?? BASEMAPS[2].style) },
        layers: (props.layers as MapLayer[] | undefined) ?? [],
      };
      // La carte qui bouge pousse sa caméra à l'autre ; l'écho (vue identique)
      // est ignoré, ce qui évite toute boucle.
      const follow =
        (other: React.RefObject<MapViewHandle | null>) =>
        (v: { center: [number, number]; zoom: number; pitch: number; bearing: number }) => {
          const view = { center: v.center, zoom: v.zoom, pitch: v.pitch, bearing: v.bearing };
          if (lastView.current && same(lastView.current, view)) return;
          lastView.current = view;
          other.current?.flyTo(view, true);
        };
      const common = {
        themeColors: ctx.theme?.colors,
        getAuthToken: client.getAuthToken,
        getCoreUrl: client.getCoreUrl,
        getShareLinkToken: client.getShareLinkToken,
        loadCustomIcon: (iconId: string) => client.fetchMapIconBlob(iconId),
      };
      return (
        <div className="relative h-full w-full overflow-hidden">
          <Suspense
            fallback={<div className="text-xs text-ink-2">{t("widgetMap.loadingFallback")}</div>}
          >
            <div className="absolute inset-0">
              <MapView
                ref={left}
                config={leftConfig}
                onViewChange={follow(right)}
                hideLegend
                {...common}
              />
            </div>
            <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${pos}%)` }}>
              <MapView
                ref={right}
                config={rightConfig}
                onViewChange={follow(left)}
                hideLegend
                {...common}
              />
            </div>
          </Suspense>
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 w-0.5 bg-accent"
            style={{ left: `${pos}%` }}
          />
          <input
            type="range"
            min={0}
            max={100}
            value={pos}
            aria-label={t("widgetSwipe.sliderAria")}
            className="absolute bottom-3 left-1/2 w-2/3 -translate-x-1/2"
            onChange={(e) => setPos(Number(e.target.value))}
          />
        </div>
      );
    },
  });
}
