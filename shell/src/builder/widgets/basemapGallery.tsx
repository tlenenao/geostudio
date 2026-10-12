// SPDX-License-Identifier: Apache-2.0
// ARC-26 : galerie de fonds de carte. Choisit un fond parmi BASEMAPS et émet
// `basemapChanged` ({ style }) ; câblé par une action vers l'action
// `setBasemap` d'un widget carte (aucune logique cachée hors config).
import { useState } from "react";
import { registerWidget } from "../registry";
import { BASEMAPS } from "../../map/basemaps";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";

export function registerBasemapGalleryWidget(): void {
  registerWidget({
    type: "basemapGallery",
    label: t("widgetBasemapGallery.paletteLabel"),
    defaultProps: { title: "" },
    defaultSize: { w: 4, h: 3 },
    events: ["basemapChanged"],
    configSchema: [
      { name: "title", type: "string", label: t("widgetBasemapGallery.titleConfig"), default: "" },
    ],
    PropsPanel: ({ props, onChange }) => (
      <label className="flex flex-col gap-1 text-sm">
        {t("widgetBasemapGallery.titleConfig")}
        <input
          className="h-9 rounded-md border border-control bg-surface px-2 text-ink"
          value={String(props.title ?? "")}
          onChange={(e) => onChange({ ...props, title: e.target.value })}
        />
      </label>
    ),
    Component: ({ props, ctx }) => {
      const [selected, setSelected] = useState(BASEMAPS[0].style);
      const title = String(props.title ?? "") || t("widgetBasemapGallery.defaultTitle");
      return (
        <div role="radiogroup" aria-label={title} className="flex h-full flex-col gap-2 p-2">
          <p className="text-sm font-medium text-ink">{title}</p>
          <div className="grid grid-cols-2 gap-2">
            {BASEMAPS.map((b) => (
              <button
                key={b.id}
                type="button"
                role="radio"
                aria-checked={selected === b.style}
                className="rounded-md border border-control bg-surface px-3 py-4 text-sm text-ink aria-checked:border-accent aria-checked:bg-accent-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                onClick={() => {
                  setSelected(b.style);
                  ctx.bus?.emit(ctx.widgetId ?? "", "basemapChanged", { style: b.style });
                }}
              >
                {b.label}
              </button>
            ))}
          </div>
        </div>
      );
    },
  });
}
