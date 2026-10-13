// SPDX-License-Identifier: Apache-2.0
// ARC-33 : ajout d'une couche raster hébergée (COG servi par le cœur sous can()) — choix de
// l'item, rampe de couleurs et étendue de valeurs (préremplie depuis les stats de la bande 1).
// La rampe et l'étendue vivent dans `tilesUrl` : elles survivent donc à un rechargement sans
// nouveau champ de config (pas de piège toFrontLayer, `kind: "raster"` existe déjà).
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { MapLayer } from "../api/types";
import { Button } from "../ui/kit/Button";
import { RasterUploadButton } from "./RasterUploadButton";
import { t } from "../i18n";
import "../i18n/domains/map";

export const RASTER_COLORMAPS = ["viridis", "magma", "terrain", "greys", "rdylgn"] as const;

export function rasterTilesUrl(
  coreUrl: string,
  itemId: string,
  colormap: string,
  min: number,
  max: number,
): string {
  const q = new URLSearchParams({ rescale: `${min},${max}`, colormap_name: colormap });
  return `${coreUrl}/raster/${itemId}/tiles/{z}/{x}/{y}?${q.toString()}`;
}

export function RasterLayerForm({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const client = useItemClient();
  const sources = useQuery({
    queryKey: ["raster-sources"],
    queryFn: () => client.listHostedRasterSources(),
  });
  const [itemId, setItemId] = useState("");
  const [colormap, setColormap] = useState<string>("viridis");
  const [min, setMin] = useState("0");
  const [max, setMax] = useState("1");
  const info = useQuery({
    queryKey: ["raster-info", itemId],
    queryFn: () => client.getRasterInfo(itemId),
    enabled: itemId !== "",
  });

  useEffect(() => {
    const band = info.data?.bands[0];
    if (band?.min != null && band.max != null) {
      setMin(String(band.min));
      setMax(String(band.max));
    }
  }, [info.data]);

  function add(id: string) {
    const coreUrl = client.getCoreUrl?.();
    const lo = Number(min);
    const hi = Number(max);
    if (!coreUrl || !id || !Number.isFinite(lo) || !Number.isFinite(hi)) return;
    const title = sources.data?.find((s) => s.id === id)?.title ?? id;
    onAdd({
      id: crypto.randomUUID(),
      title,
      visible: true,
      kind: "raster",
      tilesUrl: rasterTilesUrl(coreUrl, id, colormap, lo, hi),
      opacity: 1,
    });
  }

  return (
    <div className="border-t border-rule pt-2">
      <p className="mb-1 text-xs font-medium text-ink-2">{t("rasterLayer.heading")}</p>
      <div className="flex flex-col gap-1">
        <select
          aria-label={t("rasterLayer.itemAria")}
          className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink"
          value={itemId}
          onChange={(e) => setItemId(e.target.value)}
        >
          <option value="">{t("rasterLayer.chooseOption")}</option>
          {(sources.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
        <select
          aria-label={t("rasterLayer.colormapAria")}
          className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink"
          value={colormap}
          onChange={(e) => setColormap(e.target.value)}
        >
          {RASTER_COLORMAPS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <div className="flex gap-1">
          <input
            aria-label={t("rasterLayer.minAria")}
            type="number"
            className="h-9 w-full rounded-md border border-control bg-surface px-2 text-sm text-ink"
            value={min}
            onChange={(e) => setMin(e.target.value)}
          />
          <input
            aria-label={t("rasterLayer.maxAria")}
            type="number"
            className="h-9 w-full rounded-md border border-control bg-surface px-2 text-sm text-ink"
            value={max}
            onChange={(e) => setMax(e.target.value)}
          />
        </div>
        <Button
          type="button"
          size="sm"
          className="w-fit"
          disabled={!itemId}
          onClick={() => add(itemId)}
        >
          {t("rasterLayer.addButton")}
        </Button>
        <RasterUploadButton
          onUploaded={(id) => {
            void sources.refetch();
            setItemId(id);
          }}
        />
      </div>
    </div>
  );
}
