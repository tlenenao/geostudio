// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLayerSources } from "../api/hooks";
import type { LayerSource, MapLayer } from "../api/types";
import { detectGeometryKind, renderAsFor } from "../builder/widgets/mapSymbology";
import { fetchFeatureCollection } from "./geojsonIntrospect";
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";

function toMapLayer(source: LayerSource): MapLayer {
  const id = crypto.randomUUID();
  if (source.kind === "vector") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "vector",
      tilesUrl: source.tilesUrl ?? "",
      sourceLayer: source.sourceLayer ?? "",
      collectionId: source.collectionId,
      geometryKind: source.geometryKind,
      pkColumn: source.pkColumn,
    };
  }
  if (source.kind === "raster") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "raster",
      tilesUrl: source.tilesUrl ?? "",
      opacity: 1,
    };
  }
  if (source.kind === "tiles3d") {
    return { id, title: source.title, visible: true, kind: "tiles3d", url: source.url ?? "" };
  }
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
}

export function LayerPicker({ onAdd }: { onAdd: (layer: MapLayer) => void }) {
  const [q, setQ] = useState("");
  const [tiles3dTitle, setTiles3dTitle] = useState("");
  const [tiles3dUrl, setTiles3dUrl] = useState("");
  const [featureTitle, setFeatureTitle] = useState("");
  const [featureUrl, setFeatureUrl] = useState("");
  const [featureError, setFeatureError] = useState<string | null>(null);
  const [featureBusy, setFeatureBusy] = useState(false);
  const [deckTitle, setDeckTitle] = useState("");
  const [deckType, setDeckType] = useState<"heatmap" | "hexbin" | "column">("heatmap");
  const [deckUrl, setDeckUrl] = useState("");
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useLayerSources({ q: q || undefined });

  async function addFeatureLayer() {
    const title = featureTitle.trim();
    const url = featureUrl.trim();
    if (!title || !url) return;
    setFeatureBusy(true);
    setFeatureError(null);
    let renderAs: "fill" | "circle" | "line" | undefined;
    try {
      const fc = await fetchFeatureCollection(url);
      renderAs = renderAsFor(detectGeometryKind(fc.features[0]?.geometry));
      // Amorce le cache que LayersPanel.tsx lit sous la même clé
      // (useFeatureLayerGeoJson) : ouvrir tout de suite le panneau de
      // symbologie de cette couche ne refait pas ce fetch.
      queryClient.setQueryData(["feature-geojson", url], fc);
    } catch {
      // L'URL est ajoutée quand même : la même URL, si elle échoue ici
      // (CORS, en-têtes différents...), échouera de la même façon pour
      // MapLibre au rendu — ce n'est pas une régression, juste un défaut
      // qu'on ne peut pas prédire sans que MapView tente lui-même le rendu.
      setFeatureError(t("layerPicker.contentVerifyError"));
    }
    onAdd({
      id: crypto.randomUUID(),
      title,
      visible: true,
      kind: "feature",
      url,
      ...(renderAs ? { renderAs } : {}),
    });
    setFeatureTitle("");
    setFeatureUrl("");
    setFeatureBusy(false);
  }

  function addDeckLayer() {
    if (!deckTitle.trim() || !deckUrl.trim()) return;
    onAdd({
      id: crypto.randomUUID(),
      title: deckTitle,
      visible: true,
      kind: "deck",
      deckType,
      dataUrl: deckUrl,
    });
    setDeckTitle("");
    setDeckUrl("");
  }

  function addTiles3D() {
    if (!tiles3dTitle.trim() || !tiles3dUrl.trim()) return;
    onAdd({
      id: crypto.randomUUID(),
      title: tiles3dTitle,
      visible: true,
      kind: "tiles3d",
      url: tiles3dUrl,
    });
    setTiles3dTitle("");
    setTiles3dUrl("");
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        type="search"
        role="searchbox"
        aria-label={t("layerPicker.searchAria")}
        placeholder={t("layerPicker.searchPlaceholder")}
        className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {isLoading && <p className="text-sm text-ink-2">{t("layerPicker.loadingSources")}</p>}
      {isError && (
        <div className="text-sm text-danger">
          <p role="alert">{t("layerPicker.loadError")}</p>
          <button type="button" className="underline" onClick={() => void refetch()}>
            {t("common.retry")}
          </button>
        </div>
      )}
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-ink-2">{t("layerPicker.emptyText")}</p>
      )}
      {!isLoading && !isError && data && data.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.map((source) => (
            <li key={`${source.service}:${source.id}`}>
              <button
                type="button"
                className="w-full rounded-md px-2 py-1 text-left text-sm text-ink hover:bg-sunken"
                onClick={() => onAdd(toMapLayer(source))}
              >
                {source.title}
                <span className="ml-2 text-xs text-ink-3">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-ink-3">
                    {t("layerPicker.featureCountTemplate", { n: source.featureCount })}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="border-t border-rule pt-2">
        <p className="mb-1 text-xs font-medium text-ink-2">
          {t("layerPicker.addTileset3dHeading")}
        </p>
        <div className="flex flex-col gap-1">
          <input
            aria-label={t("layerPicker.tileset3dTitleAria")}
            type="text"
            placeholder={t("layerPicker.titlePlaceholder")}
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={tiles3dTitle}
            onChange={(e) => setTiles3dTitle(e.target.value)}
          />
          <input
            aria-label={t("layerPicker.tileset3dUrlAria")}
            type="text"
            placeholder={t("layerPicker.tileset3dUrlPlaceholder")}
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={tiles3dUrl}
            onChange={(e) => setTiles3dUrl(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!tiles3dTitle.trim() || !tiles3dUrl.trim()}
            onClick={addTiles3D}
          >
            {t("layerPicker.addTileset3dButton")}
          </Button>
        </div>
      </div>
      <div className="border-t border-rule pt-2">
        <p className="mb-1 text-xs font-medium text-ink-2">{t("layerPicker.addDeckHeading")}</p>
        <div className="flex flex-col gap-1">
          <input
            aria-label={t("layerPicker.deckTitleAria")}
            type="text"
            placeholder={t("layerPicker.titlePlaceholder")}
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={deckTitle}
            onChange={(e) => setDeckTitle(e.target.value)}
          />
          <select
            aria-label={t("layerPicker.deckTypeAria")}
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={deckType}
            onChange={(e) => setDeckType(e.target.value as "heatmap" | "hexbin" | "column")}
          >
            <option value="heatmap">{t("layerPicker.deckHeatmapOption")}</option>
            <option value="hexbin">{t("layerPicker.deckHexbinOption")}</option>
            <option value="column">{t("layerPicker.deckColumnOption")}</option>
          </select>
          <input
            aria-label={t("layerPicker.deckUrlAria")}
            type="text"
            placeholder={t("layerPicker.geojsonUrlPlaceholder")}
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={deckUrl}
            onChange={(e) => setDeckUrl(e.target.value)}
          />
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!deckTitle.trim() || !deckUrl.trim()}
            onClick={addDeckLayer}
          >
            {t("layerPicker.addDeckButton")}
          </Button>
        </div>
      </div>
      <div className="border-t border-rule pt-2">
        <p className="mb-1 text-xs font-medium text-ink-2">{t("layerPicker.addFeatureHeading")}</p>
        <div className="flex flex-col gap-1">
          <input
            aria-label={t("layerPicker.featureTitleAria")}
            type="text"
            placeholder={t("layerPicker.titlePlaceholder")}
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={featureTitle}
            onChange={(e) => setFeatureTitle(e.target.value)}
          />
          <input
            aria-label={t("layerPicker.featureUrlAria")}
            type="text"
            placeholder={t("layerPicker.geojsonUrlPlaceholder")}
            className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
            value={featureUrl}
            onChange={(e) => setFeatureUrl(e.target.value)}
          />
          {featureError && (
            <p role="alert" className="text-xs text-warn">
              {featureError}
            </p>
          )}
          <Button
            type="button"
            size="sm"
            className="w-fit"
            disabled={!featureTitle.trim() || !featureUrl.trim() || featureBusy}
            onClick={() => void addFeatureLayer()}
          >
            {t("layerPicker.addFeatureButton")}
          </Button>
        </div>
      </div>
    </div>
  );
}
