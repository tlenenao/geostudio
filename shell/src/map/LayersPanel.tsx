// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import type { MapLayer } from "../api/types";
import {
  fetchFeatureCollection,
  hostedToken,
  listFields,
  makeSampleFieldFn,
  makeStatQueryFn,
} from "./geojsonIntrospect";
import { LayerPicker } from "./LayerPicker";
import { isHostedCollectionUrl } from "./hostedCoreUrl";
import { MapSymbologyEditor } from "./MapSymbologyEditor";
import { PopupEditor } from "./PopupEditor";
import { tileKeys, useViewport } from "./viewportTiles";
import { usePanelTrigger } from "../ui/kit/usePanelTrigger";
import { t } from "../i18n";

// Une couche "feature" n'a pas de collection interrogeable : son schéma vient
// du GeoJSON qu'elle pointe elle-même. Une seule requête partagée par les
// deux éditeurs ci-dessous (react-query dédoublonne par clé — un seul fetch
// réseau même si popup et symbologie sont montés en même temps, ce qui est
// le cas ici).
function useFeatureLayerGeoJson(layer: Extract<MapLayer, { kind: "vector" | "feature" }>) {
  const client = useItemClient();
  const url = layer.kind === "feature" ? layer.url : undefined;
  return useQuery({
    queryKey: ["feature-geojson", url],
    queryFn: () => fetchFeatureCollection(url!, hostedToken(client, url!)),
    enabled: Boolean(url),
  });
}

// Charge le schéma de la collection sous-jacente pour offrir la liste des
// champs à l'auteur — patron déjà établi par CrossFilterLinkEditor.tsx:28-34
// (useQuery inline, pas de hook dédié dans api/hooks.ts pour ce besoin).
function LayerPopupEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const client = useItemClient();
  const collectionId = layer.kind === "vector" ? layer.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: Boolean(collectionId),
  });
  const featureGeojson = useFeatureLayerGeoJson(layer);
  return (
    <PopupEditor
      value={layer.popup}
      // Sans collectionId : couche "feature" (URL GeoJSON), les champs
      // viennent de l'introspection côté client (geojsonIntrospect.ts,
      // Task 2 SP-28) une fois son fetch résolu ; avant ça, liste vide comme
      // pour une collection dont le schéma charge encore.
      availableFields={
        collectionId
          ? (schema.data?.fields.filter((f) => f.type !== "attachment").map((f) => f.name) ?? [])
          : featureGeojson.data
            ? listFields(featureGeojson.data)
            : []
      }
      attachmentFields={
        collectionId
          ? (schema.data?.fields.filter((f) => f.type === "attachment").map((f) => f.name) ?? [])
          : []
      }
      onChange={(popup) => onChangeLayer({ ...layer, popup })}
    />
  );
}

// Même patron que LayerPopupEditor ci-dessus. Sans collectionId (couche
// "feature", URL GeoJSON) : les trois fonctions que MapSymbologyEditor
// attend (availableFields/runStatistics/sampleField) sont dérivées du
// GeoJSON introspecté côté client (Task 2, SP-28) au lieu d'une requête au
// cœur — jenksAvailable reste à son défaut `true` : contrairement à la
// couche "feature" du widget carte (mapWidget.tsx, adossée à un DataSource
// distant sans valeurs brutes disponibles), ici les valeurs sont locales et
// Jenks fonctionne réellement.
function LayerSymbologyEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const client = useItemClient();
  const collectionId = layer.kind === "vector" ? layer.collectionId : undefined;
  const schema = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId!),
    enabled: Boolean(collectionId),
  });
  const featureGeojson = useFeatureLayerGeoJson(layer);
  const fc = featureGeojson.data;
  const notReady = async (): Promise<never> => {
    throw new Error(t("layersPanel.geojsonNotLoadedError"));
  };
  return (
    <MapSymbologyEditor
      value={layer.symbology}
      availableFields={
        collectionId
          ? (schema.data?.fields.filter((f) => f.type !== "attachment").map((f) => f.name) ?? [])
          : fc
            ? listFields(fc)
            : []
      }
      themeColors={undefined} // no Theme on a standalone MapConfig (spec §1)
      runStatistics={
        collectionId
          ? (query) =>
              client.queryDataSource({
                id: `map-symbology-${collectionId}`,
                type: "statistics",
                service: "core",
                layer: collectionId,
                query,
              })
          : fc
            ? makeStatQueryFn(fc)
            : notReady
      }
      sampleField={
        collectionId
          ? (field, limit) => client.sampleCollectionField(collectionId, field, limit)
          : fc
            ? makeSampleFieldFn(fc)
            : notReady
      }
      // `?.()` OBLIGATOIRE, pas cosmétique (défaut n° 5 de la brief Task 12) :
      // ce hôte est rendu dans des tests existants avec des ItemClient
      // PARTIELS (LayersPanel.test.tsx:48 et :103). Sans `?.`,
      // `client.listMapIcons()` lève SYNCHRONIQUEMENT dans le callback
      // d'effet et fait échouer le rendu de ces tests, verts aujourd'hui —
      // le `.catch()` de l'effet n'attrape rien, il n'y a pas encore de
      // promesse.
      listCustomIcons={() => client.listMapIcons?.() ?? Promise.resolve([])}
      uploadCustomIcon={(file, title, category) =>
        // UN SEUL appel (D7) : plus de presign → PUT → POST. Le cœur reçoit
        // les octets, choisit la clé S3, assainit, puis écrit.
        client.uploadMapIcon(file, title, category)
      }
      deleteCustomIcon={(id) => client.deleteMapIcon(id)}
      onChange={(symbology) => onChangeLayer({ ...layer, symbology })}
    />
  );
}

// GAP-45 : layer.paint fait un round-trip API complet (toFrontLayer()) et
// sert de repli au rendu quand symbology est absent, mais aucune UI ne
// l'écrivait jamais avant ce panneau — seul un document édité hors produit
// (MCP/API) pouvait l'utiliser. Repliée par défaut (mode « Avancé »
// explicite, pas un formulaire structuré par propriété MapLibre — rule
// CLAUDE.md n°2, `paint` reste une échappatoire volontaire). État local
// `draft` distinct de `layer.paint` tant que le JSON n'est pas valide, pour
// ne jamais perdre la frappe de l'auteur sur une faute de frappe
// temporaire ; un JSON invalide affiche une erreur sans jamais committer
// une peinture cassée (onChangeLayer n'est appelé qu'après parse réussi).
function LayerPaintAdvancedEditor({
  layer,
  onChangeLayer,
}: {
  layer: Extract<MapLayer, { kind: "vector" | "feature" }>;
  onChangeLayer: (next: MapLayer) => void;
}) {
  const [open, setOpen] = useState(false);
  const panel = usePanelTrigger(open);
  const [draft, setDraft] = useState(() => JSON.stringify(layer.paint ?? {}, null, 2));
  const [error, setError] = useState<string | null>(null);
  function commit() {
    try {
      const parsed = JSON.parse(draft) as Record<string, unknown>;
      setError(null);
      onChangeLayer({ ...layer, paint: parsed });
    } catch {
      setError(t("layersPanel.paintInvalidJson"));
    }
  }
  return (
    <div className="basis-full pl-2">
      <button
        type="button"
        {...panel.triggerProps}
        className="text-xs underline"
        onClick={() => setOpen((o) => !o)}
      >
        {t("layersPanel.paintAdvancedButton")}
      </button>
      {open && (
        <div id={panel.panelId}>
          <textarea
            aria-label={t("layersPanel.paintAria")}
            className="mt-1 h-24 w-full rounded-md border border-rule bg-surface p-2 font-mono text-xs"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
          />
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// Boutons-icônes d'une couche : 24 px minimum (WCAG 2.5.8), 44 px sur pointeur
// grossier (P31.08).
const ICON_BTN =
  "inline-flex min-h-6 min-w-6 items-center justify-center px-1 pointer-coarse:min-h-11 pointer-coarse:min-w-11";

export function LayersPanel({
  layers,
  onChange,
}: {
  layers: MapLayer[];
  onChange: (layers: MapLayer[]) => void;
}) {
  const client = useItemClient();
  const [truncatedLayerIds, setTruncatedLayerIds] = useState<Set<string>>(new Set());
  const vectorLayers = layers.filter(
    (l): l is Extract<MapLayer, { kind: "vector" }> => l.kind === "vector",
  );
  // Clé dérivée (id+tilesUrl) plutôt que `layers` en dépendance directe :
  // `layers` change de référence à chaque onChange du panneau (bascule de
  // visibilité, réordonnancement, opacité...), ce qui redéclencherait la
  // sonde réseau sur des changements sans rapport avec l'ensemble des
  // couches vecteur réellement affichées.
  const viewport = useViewport();
  // Tuiles réellement affichées (vue courante), pas la seule 0/0/0 : le badge
  // disparaît quand on zoome sur une zone complète (P29.06). Sans vue publiée
  // (carte pas encore chargée), on retombe sur la tuile racine.
  const tiles = viewport ? tileKeys(viewport) : ["0/0/0"];
  const vectorLayersKey = vectorLayers.map((l) => `${l.id}::${l.tilesUrl}`).join("|");
  const probeKey = `${vectorLayersKey}@${tiles.join(",")}`;

  useEffect(() => {
    if (vectorLayers.length === 0) {
      setTruncatedLayerIds(new Set());
      return;
    }
    let cancelled = false;
    void Promise.all(
      vectorLayers.map(async (layer) => {
        // MapLibre ne remonte pas les en-têtes de réponse : on sonde nous-mêmes
        // les tuiles visibles (cache HTTP du navigateur, max-age 300).
        // `?.()` obligatoire : plusieurs hôtes/tests passent un ItemClient PARTIEL.
        // Jeton attaché UNIQUEMENT si la tuile est servie par le cœur (revue
        // finale Vague B, C2) ; getCoreUrl absent => « non hébergé ».
        const probes = await Promise.all(
          tiles.map(async (key) => {
            const url = layer.tilesUrl.replace("{z}/{x}/{y}", key);
            const token = isHostedCollectionUrl(url, client.getCoreUrl?.())
              ? client.getAuthToken?.()
              : undefined;
            try {
              const res = await fetch(url, {
                headers: token ? { Authorization: `Bearer ${token}` } : undefined,
              });
              return res.headers.get("X-Tile-Truncated") === "true";
            } catch {
              return false;
            }
          }),
        );
        return [layer.id, probes.some(Boolean)] as const;
      }),
    ).then((results) => {
      if (cancelled) return;
      setTruncatedLayerIds(new Set(results.filter(([, truncated]) => truncated).map(([id]) => id)));
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [probeKey, client]);

  function toggle(id: string) {
    onChange(layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)));
  }
  function remove(id: string) {
    onChange(layers.filter((l) => l.id !== id));
  }
  function move(index: number, delta: number) {
    const next = index + delta;
    if (next < 0 || next >= layers.length) return;
    const copy = [...layers];
    [copy[index], copy[next]] = [copy[next], copy[index]];
    onChange(copy);
  }
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-1">
        {layers.map((layer, i) => (
          <li
            key={layer.id}
            className="flex flex-wrap items-center gap-2 text-sm"
            // flex-wrap : sans lui, le bloc `basis-full` (édition inline,
            // ci-dessous) ne peut jamais passer à la ligne — il écrase le titre à
            // largeur 0 à la place (SP-36).
          >
            <span className="flex-1 truncate">{layer.title}</span>
            {layer.kind === "vector" && truncatedLayerIds.has(layer.id) && (
              <span
                className="rounded bg-warn-soft px-1.5 py-0.5 text-xs text-warn"
                title={t("layersPanel.truncatedBadge")}
              >
                {t("layersPanel.truncatedBadge")}
              </span>
            )}
            <button
              type="button"
              aria-label={t("layersPanel.moveUpAria", { title: layer.title })}
              disabled={i === 0}
              className={`${ICON_BTN} disabled:opacity-30`}
              onClick={() => move(i, -1)}
            >
              ↑
            </button>
            <button
              type="button"
              aria-label={t("layersPanel.moveDownAria", { title: layer.title })}
              disabled={i === layers.length - 1}
              className={`${ICON_BTN} disabled:opacity-30`}
              onClick={() => move(i, 1)}
            >
              ↓
            </button>
            <button
              type="button"
              aria-label={
                layer.visible
                  ? t("layersPanel.hideAria", { title: layer.title })
                  : t("layersPanel.showAria", { title: layer.title })
              }
              className={ICON_BTN}
              onClick={() => toggle(layer.id)}
            >
              {layer.visible ? "👁" : "🚫"}
            </button>
            <button
              type="button"
              aria-label={t("layersPanel.removeAria", { title: layer.title })}
              className={`${ICON_BTN} text-danger`}
              onClick={() => remove(layer.id)}
            >
              ✕
            </button>
            {layer.kind === "deck" && (
              <div className="basis-full pl-2">
                {/* Clés de props alignées sur l'API réelle des layers deck.gl
                    sous-jacents (buildDeckLayer, MapView.tsx) — vérifiées
                    contre les .d.ts installés, pas devinées : HeatmapLayer
                    n'a pas de prop "radius" (radiusPixels), HexagonLayer a
                    "radius" (mètres), ColumnLayer a "elevationScale". */}
                {layer.deckType === "heatmap" && (
                  <label className="flex flex-col gap-1 text-sm">
                    {t("layersPanel.radiusPixelsLabel")}
                    <input
                      aria-label={t("layersPanel.radiusPixelsLabel")}
                      type="number"
                      min={1}
                      value={Number(
                        (layer.props as { radiusPixels?: number } | undefined)?.radiusPixels ?? 30,
                      )}
                      onChange={(e) =>
                        onChange(
                          layers.map((l) =>
                            l.id === layer.id
                              ? {
                                  ...layer,
                                  props: { ...layer.props, radiusPixels: Number(e.target.value) },
                                }
                              : l,
                          ),
                        )
                      }
                    />
                  </label>
                )}
                {layer.deckType === "hexbin" && (
                  <label className="flex flex-col gap-1 text-sm">
                    {t("layersPanel.radiusMetersLabel")}
                    <input
                      aria-label={t("layersPanel.radiusMetersLabel")}
                      type="number"
                      min={1}
                      value={Number(
                        (layer.props as { radius?: number } | undefined)?.radius ?? 1000,
                      )}
                      onChange={(e) =>
                        onChange(
                          layers.map((l) =>
                            l.id === layer.id
                              ? {
                                  ...layer,
                                  props: { ...layer.props, radius: Number(e.target.value) },
                                }
                              : l,
                          ),
                        )
                      }
                    />
                  </label>
                )}
                {layer.deckType === "column" && (
                  <label className="flex flex-col gap-1 text-sm">
                    {t("layersPanel.elevationScaleLabel")}
                    <input
                      aria-label={t("layersPanel.elevationScaleLabel")}
                      type="number"
                      min={0}
                      value={Number(
                        (layer.props as { elevationScale?: number } | undefined)?.elevationScale ??
                          1,
                      )}
                      onChange={(e) =>
                        onChange(
                          layers.map((l) =>
                            l.id === layer.id
                              ? {
                                  ...layer,
                                  props: { ...layer.props, elevationScale: Number(e.target.value) },
                                }
                              : l,
                          ),
                        )
                      }
                    />
                  </label>
                )}
              </div>
            )}
            {layer.kind === "raster" && (
              <div className="basis-full pl-2">
                <label className="flex flex-col gap-1 text-sm">
                  {t("layersPanel.opacityLabel", {
                    percent: Math.round((layer.opacity ?? 1) * 100),
                  })}
                  <input
                    aria-label={t("layersPanel.opacityAria")}
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={layer.opacity ?? 1}
                    onChange={(e) =>
                      onChange(
                        layers.map((l) =>
                          l.id === layer.id ? { ...l, opacity: Number(e.target.value) } : l,
                        ),
                      )
                    }
                  />
                </label>
              </div>
            )}
            {(layer.kind === "vector" || layer.kind === "feature") && (
              <div className="basis-full pl-2">
                <LayerPopupEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
                <LayerSymbologyEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
                <LayerPaintAdvancedEditor
                  layer={layer}
                  onChangeLayer={(next) =>
                    onChange(layers.map((l) => (l.id === layer.id ? next : l)))
                  }
                />
              </div>
            )}
          </li>
        ))}
        {layers.length === 0 && (
          <li className="text-xs text-ink-3">{t("layersPanel.emptyText")}</li>
        )}
      </ul>
      <div className="border-t border-rule pt-2">
        <p className="mb-1 text-xs font-medium text-ink-2">{t("layersPanel.addLayerHeading")}</p>
        <LayerPicker onAdd={(layer) => onChange([...layers, layer])} />
      </div>
    </div>
  );
}
