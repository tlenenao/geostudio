// SPDX-License-Identifier: Apache-2.0
import "maplibre-gl/dist/maplibre-gl.css";
import "./maplibreWorkerSetup";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import * as maplibregl from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { DataRecord, MapConfig, ThemeColors } from "../api/types";
import { MapLegend } from "./MapLegend";
import { MapMeasureSketchToolbar } from "./MapMeasureSketchToolbar";
import { MapPopup } from "./MapPopup";
import { useMapPopup } from "./useMapPopup";
import { resolvePopupContent } from "./popupContent";
import { publishViewport } from "./viewportTiles";
import { t } from "../i18n";
import { isHostedCollectionUrl, isHostedTerrainUrl } from "./hostedCoreUrl";
import { HIGHLIGHT_ID } from "./mapLayerBuild";
import {
  applyLayers,
  loadIconImages,
  refreshLabelSources,
  mapRelevantLayer,
} from "./mapApplyLayers";
import {
  tilesetKey,
  applyDeckLayers,
  releaseLumaCanvasObserver,
  applyTerrain,
} from "./mapDeckTerrain";

export type MapViewHandle = {
  // `instant` : saut sans animation (saisie numérique de la caméra — un vol
  // interrompu par la frappe suivante émet un `moveend` à mi-course qui
  // écrasait l'inclinaison saisie dans le brouillon).
  flyTo: (
    opts: {
      center: [number, number];
      zoom?: number;
      pitch?: number;
      bearing?: number;
    },
    instant?: boolean,
  ) => void;
  highlight: (geometry: unknown | null) => void;
  fitBounds: (
    bbox: [number, number, number, number],
    opts?: { padding?: number; maxZoom?: number },
  ) => void;
};

export const MapView = forwardRef<
  MapViewHandle,
  {
    config: MapConfig;
    onViewChange?: (v: {
      center: [number, number];
      zoom: number;
      bbox: [number, number, number, number];
      pitch: number;
      bearing: number;
    }) => void;
    onFeatureClick?: (record: DataRecord) => void;
    // Fired once the map has settled after its first load (MapLibre "idle":
    // no pending tiles/style/sprite loads) *and* every visible tiles3d layer's
    // root tileset has loaded — the real "ready to capture" signal for
    // exportRender mode (SP-17a Task 10), as opposed to a fixed delay.
    // MapLibre knows nothing about deck.gl's Tile3DLayer streaming, so "idle"
    // on its own would let a capture happen with the tileset still missing.
    onReady?: () => void;
    // Suppresses the built-in interactive legend. Used by exportRender mode
    // (MapEditorPage), which renders its own legend overlay driven by
    // `printLayout.showLegend` — without this, that toggle couldn't ever
    // hide the legend from a capture (this MapLegend would still render
    // underneath it, and both would duplicate when showLegend is true).
    hideLegend?: boolean;
    // Couleurs de thème résolvant `palette: "theme-primary"` dans la
    // symbologie (Task 6/19) — sans elle, cette palette dégrade sur son
    // repli neutre.
    themeColors?: ThemeColors;
    // Monte la barre d'outils mesure/croquis (Task 16 de SP-27) : jamais
    // câblé par défaut, aucun site de montage existant ne le passe encore.
    interactiveTools?: boolean;
    // Authenticates Tile3DLayer requests against a hosted (design
    // /tileset3d/) tileset's proxy route — never sent for external tileset
    // URLs (see HOSTED_TILESET3D_PATH check in buildTiles3DLayer). Absent by
    // default: a MapView with no hosted tiles3d layer needs no auth plumbing.
    getAuthToken?: () => string | undefined;
    // The core API's base URL, used alongside getAuthToken to verify a
    // tiles3d layer's URL actually belongs to our own authenticated proxy
    // (origin+path check) before attaching a bearer token — see
    // isHostedTilesetUrl. Absent by default, same as getAuthToken.
    getCoreUrl?: () => string;
    // Jeton invité d'un lien de partage à échéance (GAP-19, Task 10) —
    // n'est jamais fourni en même temps qu'un token d'auth réel qui
    // "marche" : quand getAuthToken en renvoie un, il prime toujours et
    // getShareLinkToken n'est même pas appelé. Sert le même rôle que
    // getAuthToken sur les mêmes URLs hébergées (tuiles + pièces
    // jointes), mais avec l'en-tête `X-Share-Link-Token` au lieu
    // d'`Authorization` — jamais les deux à la fois sur une même requête.
    getShareLinkToken?: () => string | undefined;
    // Récupère un blob d'icône personnalisée (fetch authentifié via
    // ItemClient), passé à `decodeIconImage` par `loadIconImages`. Absent par
    // défaut : un MapView sans icône personnalisée n'a besoin d'aucun
    // câblage (Task 12 le fournit depuis les deux hôtes).
    loadCustomIcon?: (iconId: string) => Promise<Blob>;
  }
  // Il n'y a délibérément pas de prop `exprContext` : le gabarit de popup
  // n'a qu'un seul vocabulaire, `record.*` (cf. popupContent.ts). La prop
  // existait, mais aucun site de montage réel ne la passait — I4 de la revue
  // finale SP-24 — et aucun n'a de quoi la remplir : MapEditorPage n'a ni
  // variables ni contexte d'app, et ni mapWidget ni ExplorerDrawer n'exposent
  // l'ExprContext de l'ActionBus au rendu. Une capacité annoncée par
  // l'éditeur et vide à l'exécution est pire que pas de capacité.
>(function MapView(
  {
    config,
    onViewChange,
    onFeatureClick,
    onReady,
    hideLegend,
    themeColors,
    interactiveTools,
    getAuthToken,
    getCoreUrl,
    getShareLinkToken,
    loadCustomIcon,
  },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const appliedRef = useRef<Set<string>>(new Set());
  const clickHandlersRef = useRef<Map<string, (e: maplibregl.MapLayerMouseEvent) => void>>(
    new Map(),
  );
  // Dernière charge POSÉE par source d'étiquettes, pour ne jamais rappeler
  // setData avec un contenu identique. C'est le garde du constat N3 : sans
  // lui, `idle` → setData → événement « content » → reload de tuiles →
  // repaint → `idle` s'auto-entretient à ~6 Hz, indéfiniment, sur toute carte
  // étiquetée.
  //
  // Ref d'instance, PAS un Map de portée module (correctif post-revue de
  // Task 14) : `appliedRef`/`clickHandlersRef` ci-dessus le sont déjà pour la
  // même raison — rien dans ce dépôt ne garantit l'unicité d'un `layer.id`
  // entre deux <MapView> montés en même temps (ex. deux widgets carte d'un
  // même tableau de bord affichant la même collection, cf. mapWidget.tsx).
  // Avec un Map de portée module, deux instances partageant un `layer.id`
  // partageaient la même entrée de garde : si l'une postait une charge, et
  // que l'autre calculait plus tard une sérialisation identique (plausible
  // quand les deux affichent la même collection), la seconde voyait
  // « inchangé » et sautait son propre setData — alors que sa source MapLibre
  // sous-jacente, un objet distinct, n'avait jamais été peuplée. Étiquettes
  // silencieusement absentes sur une des deux cartes.
  //
  // Passée en paramètre aux fonctions de portée module qui la lisent/l'écrivent
  // (addLabelLayer, applyLayers, refreshLabelSources), jamais fermée dessus,
  // même patron que `applied`/`clickHandlers` ci-dessus. Vidée avec le reste à
  // la destruction de la carte (voir le teardown de l'effet de montage). Une
  // WeakMap n'irait pas : la clé est un id de source, pas un objet.
  const lastLabelPayloadsRef = useRef<Map<string, string>>(new Map());
  // The style's *initial* load — the only real precondition of addSource /
  // addLayer / setTerrain. `map.isStyleLoaded()` was used here before and is a
  // different question ("is nothing loading right now?"): a single in-flight
  // tile request made it return false, and every config update that landed in
  // that window was silently dropped with nothing to retry it.
  const styleLoadedRef = useRef(false);
  // Export readiness (onReady) = MapLibre idle AND every visible tiles3d
  // tileset loaded. Deck.gl's Tile3DLayer streams outside MapLibre, so "idle"
  // alone can fire while a tileset is still missing from the capture.
  const idleRef = useRef(false);
  const readyFiredRef = useRef(false);
  const loadedTilesetsRef = useRef<Set<string>>(new Set());
  // Popup ouvert (état, reprojection, fermeture, pièces jointes, schéma).
  const {
    popup,
    setPopup,
    popupPoint,
    popupConfig,
    popupAttachments,
    popupSchema,
    downloadPopupAttachment,
  } = useMapPopup(mapRef, config.layers);
  // Un `useRef` assigné dans un effet ne provoque AUCUN rendu : la barre
  // d'outils conditionnée à `mapRef.current` ne se monterait jamais au
  // premier rendu. On garde donc l'instance dans un état, posé depuis le
  // handler `load` — même raison que popup/popupPoint pour MapPopup.
  const [readyMap, setReadyMap] = useState<maplibregl.Map | null>(null);
  // Mesure/croquis actif : suspend les popups de MapView. Sans cela un clic de
  // mesure sur une entité ouvre AUSSI la popup — `applyLayers` enregistre un
  // handler de clic par couche, et la popup (z-20, MapPopup.tsx:34) recouvre la
  // barre d'outils (z-10) et le texte même que les preuves E2E 4.5 de Task 20
  // asserteront. Constat I16.
  const [toolsActive, setToolsActive] = useState(false);
  // Keep the latest callback/layers reachable from the mount-time closures so
  // the async "load" and "moveend" handlers never read stale values.
  const onViewChangeRef = useRef(onViewChange);
  const onFeatureClickRef = useRef(onFeatureClick);
  const onReadyRef = useRef(onReady);
  const getAuthTokenRef = useRef(getAuthToken);
  const getCoreUrlRef = useRef(getCoreUrl);
  const getShareLinkTokenRef = useRef(getShareLinkToken);
  const loadCustomIconRef = useRef(loadCustomIcon);
  const themeColorsRef = useRef(themeColors);
  const layersRef = useRef(config.layers);
  const terrainRef = useRef(config.terrain);
  useEffect(() => {
    onViewChangeRef.current = onViewChange;
  }, [onViewChange]);
  useEffect(() => {
    onFeatureClickRef.current = onFeatureClick;
  }, [onFeatureClick]);
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);
  useEffect(() => {
    getAuthTokenRef.current = getAuthToken;
  }, [getAuthToken]);
  useEffect(() => {
    getCoreUrlRef.current = getCoreUrl;
  }, [getCoreUrl]);
  useEffect(() => {
    getShareLinkTokenRef.current = getShareLinkToken;
  }, [getShareLinkToken]);
  useEffect(() => {
    loadCustomIconRef.current = loadCustomIcon;
  }, [loadCustomIcon]);
  useEffect(() => {
    themeColorsRef.current = themeColors;
  }, [themeColors]);
  useEffect(() => {
    layersRef.current = config.layers;
  });
  useEffect(() => {
    terrainRef.current = config.terrain;
  });

  const maybeFireReady = useCallback(() => {
    if (readyFiredRef.current || !idleRef.current) return;
    const pending = layersRef.current.some(
      (l) => l.visible && l.kind === "tiles3d" && !loadedTilesetsRef.current.has(tilesetKey(l)),
    );
    if (pending) return;
    readyFiredRef.current = true;
    onReadyRef.current?.();
  }, []);

  const handleTilesetLoad = useCallback(
    (key: string) => {
      loadedTilesetsRef.current.add(key);
      maybeFireReady();
    },
    [maybeFireReady],
  );

  // Un seul clic ouvre au plus un popup : une deuxième entité cliquée
  // remplace l'état plutôt que de l'empiler (setPopup, pas un tableau).
  // La porte « cette couche a-t-elle un popup ? » est ICI et pas dans le
  // handler MapLibre : lue depuis layersRef (à jour à chaque rendu), elle
  // n'oblige pas à réenregistrer les handlers — donc à détruire et
  // reconstruire toute la carte — quand l'auteur tape dans PopupEditor
  // (I5 de la revue finale SP-24).
  const handlePopup = useCallback(
    (
      layerId: string,
      properties: Record<string, unknown>,
      lngLat: { lng: number; lat: number },
      featureId: string | number | undefined,
    ) => {
      const layer = layersRef.current.find((l) => l.id === layerId);
      if (!layer || !("popup" in layer) || !layer.popup) return;
      // `vector` ET `feature` peuvent porter `pkColumn`/`collectionId`
      // (chantier 4.12 ; Tâche 19 : le widget carte de l'App Builder/
      // `/sites/{slug}` construit toujours `kind: "feature"`, jamais
      // `vector` — les deux champs y sont optionnels et absents pour une
      // couche GeoJSON externe pure, qui reste donc sans pièces jointes).
      // `featureId` (résolu en amont par makeFeatureClickHandler — Tâche 20)
      // prime sur properties[pkColumn] : ST_AsMVT retire la colonne PK des
      // attributs quand elle est entière, elle n'existe alors que dans
      // f.id (cf. core/app/features/tiles.py::mvt_feature_id_column).
      const pkValue = featureId ?? (layer.pkColumn ? properties[layer.pkColumn] : undefined);
      const fid =
        (layer.kind === "vector" || layer.kind === "feature") && layer.pkColumn && pkValue != null
          ? String(pkValue)
          : undefined;
      setPopup({ layerId, properties, lngLat, fid });
    },
    [setPopup],
  );

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      // P30.05 : libellés des contrôles MapLibre en français.
      locale: {
        "Map.Title": t("mapView.localeMapTitle"),
        "AttributionControl.ToggleAttribution": t("mapView.localeToggleAttribution"),
        "AttributionControl.MapFeedback": t("mapView.localeMapFeedback"),
        "LogoControl.Title": t("mapView.localeLogoTitle"),
      },
      center: config.view.center,
      zoom: config.view.zoom,
      pitch: config.view.pitch ?? 0,
      bearing: config.view.bearing ?? 0,
      transformRequest: (url: string) => {
        const coreUrl = getCoreUrlRef.current?.();
        if (isHostedTerrainUrl(url, coreUrl) || isHostedCollectionUrl(url, coreUrl)) {
          const token = getAuthTokenRef.current?.();
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
          const shareToken = getShareLinkTokenRef.current?.();
          if (shareToken) return { url, headers: { "X-Share-Link-Token": shareToken } };
        }
        return { url };
      },
    });
    mapRef.current = map;
    // interleaved: deck.gl layers are inserted into MapLibre's own layer stack
    // and share its WebGL2 context + depth buffer, so 3D Tiles are correctly
    // occluded by the terrain instead of always drawing on top.
    const overlay = new MapboxOverlay({ layers: [], interleaved: true });
    overlayRef.current = overlay;
    map.addControl(overlay);
    map.on("load", () => {
      styleLoadedRef.current = true;
      setReadyMap(map);
      publishViewport({
        zoom: map.getZoom(),
        bounds: map.getBounds().toArray().flat() as [number, number, number, number],
      });
      map.addSource(HIGHLIGHT_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: HIGHLIGHT_ID,
        type: "line",
        source: HIGHLIGHT_ID,
        paint: { "line-color": "#ef4444", "line-width": 3 },
      });
      const iconImageIds = applyLayers(
        map,
        layersRef.current,
        appliedRef.current,
        clickHandlersRef.current,
        lastLabelPayloadsRef.current,
        (r) => onFeatureClickRef.current?.(r),
        handlePopup,
        themeColorsRef.current,
      );
      void loadIconImages(map, iconImageIds, loadCustomIconRef.current);
      // Un changement de config ne doit pas attendre le prochain `idle` pour
      // repeupler les étiquettes d'une couche dont les tuiles sont déjà là.
      refreshLabelSources(map, layersRef.current, lastLabelPayloadsRef.current);
      applyDeckLayers(
        overlay,
        layersRef.current,
        handleTilesetLoad,
        getAuthTokenRef.current,
        getCoreUrlRef.current,
      );
      applyTerrain(map, terrainRef.current);
      // `once()` est typé `this | Promise<any>` côté maplibre-gl (le
      // second membre de l'union ne s'applique que si aucun listener n'est
      // fourni — ici il y en a un, le retour réel est toujours `this`,
      // jamais une Promise) : `void` neutralise le faux positif de type
      // sans changer de comportement.
      void map.once("idle", () => {
        idleRef.current = true;
        maybeFireReady();
      });
    });
    // Rafraîchissement des étiquettes (constat N3) : débouncé à 150 ms ET
    // mémoïsé par source (lastLabelPayloads, dans refreshLabelSources) — les
    // deux sont nécessaires. Le debounce seul ne casserait pas la boucle
    // idle → setData → « content » → reload → repaint → idle, il ne ferait
    // que la cadencer à ~6 Hz au lieu de la fréquence de repaint brute.
    let labelDebounce: ReturnType<typeof setTimeout> | undefined;
    const scheduleLabelRefresh = () => {
      clearTimeout(labelDebounce);
      labelDebounce = setTimeout(
        () => refreshLabelSources(map, layersRef.current, lastLabelPayloadsRef.current),
        150,
      );
    };
    map.on("idle", scheduleLabelRefresh);
    map.on("moveend", () => {
      const bounds = map.getBounds().toArray().flat() as [number, number, number, number];
      publishViewport({ zoom: map.getZoom(), bounds });
      const cb = onViewChangeRef.current;
      if (!cb) return;
      const c = map.getCenter();
      cb({
        center: [c.lng, c.lat],
        zoom: map.getZoom(),
        bbox: bounds,
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      });
    });
    // Style.addLayer/addSource valident et font `return` : l'erreur part sur
    // l'event `error`, JAMAIS en exception — le try/catch d'applyLayers ne
    // voit rien et la couche disparaît en silence. Ce listener est la seule
    // chose qui rend ce mode de panne observable.
    //
    // FILTRÉ (constat N13) : MapLibre fire `error` pour toute défaillance
    // ordinaire — tuile 404, sprite manquant, style partiellement
    // inaccessible. Journaliser tout produirait un bruit permanent sur
    // demotiles.maplibre.org ou sur une collection non publique, ce qui
    // détruirait précisément la valeur de signal cherchée ici. Les erreurs du
    // validateur de style sont reconnaissables : leur message commence par
    // `layers.` / `layers[` / `sources.` / `sources[` (préfixe posé par
    // Style._validate via `layers.${id}`).
    map.on("error", (e: unknown) => {
      const message = String(
        (e as { error?: { message?: unknown } } | undefined)?.error?.message ?? "",
      );
      if (!/^(layers|sources)[.[]/.test(message)) return;
      console.error(t("mapView.styleErrorLog"), e);
    });
    return () => {
      clearTimeout(labelDebounce);
      map.off("idle", scheduleLabelRefresh);
      map.removeControl(overlay);
      releaseLumaCanvasObserver(map);
      map.remove();
      mapRef.current = null;
      setReadyMap(null);
      overlayRef.current = null;
      styleLoadedRef.current = false;
      idleRef.current = false;
      readyFiredRef.current = false;
      // La règle suggère de copier la ref dans une variable locale au
      // montage pour éviter qu'elle "ait changé" au nettoyage — mais c'est
      // précisément le comportement voulu ici : cet effet ne monte/démonte
      // qu'une fois (cf. dépendances [] ci-dessous), et on veut vider
      // l'ensemble accumulé sur toute la durée de vie du composant, pas un
      // instantané pris au montage. Même raisonnement pour
      // lastLabelPayloadsRef, ajoutée ici pour la même raison.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      loadedTilesetsRef.current.clear();
      // eslint-disable-next-line react-hooks/exhaustive-deps
      lastLabelPayloadsRef.current.clear();
    };
    // Initialize once; style/view changes are out of scope for this phase.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Identité de ce que MapLibre consomme réellement d'une couche, `popup`
  // exclu : lui n'affecte que le rendu React d'un clic déjà survenu. Sans
  // cette projection, chaque frappe dans un champ de PopupEditor produisait un
  // nouveau tableau `config.layers` et détruisait/reconstruisait TOUTES les
  // sources et couches — scintillement, re-requêtes de tuiles, et un refetch
  // complet du GeoJSON /items pour une couche `feature` (I5 de la revue
  // finale SP-24).
  const layersKey = useMemo(
    () => JSON.stringify({ layers: config.layers.map(mapRelevantLayer), themeColors }),
    [config.layers, themeColors],
  );

  useEffect(() => {
    const map = mapRef.current;
    const overlay = overlayRef.current;
    if (!map || !styleLoadedRef.current || !overlay) return;
    // layersRef, pas config.layers : l'effet ne se déclenche que sur
    // `layersKey`, mais doit appliquer les couches courantes (la ref est
    // rafraîchie par un effet déclaré plus haut, donc exécuté avant celui-ci).
    const layers = layersRef.current;
    const iconImageIds = applyLayers(
      map,
      layers,
      appliedRef.current,
      clickHandlersRef.current,
      lastLabelPayloadsRef.current,
      (r) => onFeatureClickRef.current?.(r),
      handlePopup,
      themeColorsRef.current,
    );
    void loadIconImages(map, iconImageIds, loadCustomIconRef.current);
    // Un changement de config ne doit pas attendre le prochain `idle` pour
    // repeupler les étiquettes d'une couche dont les tuiles sont déjà là.
    refreshLabelSources(map, layers, lastLabelPayloadsRef.current);
    applyDeckLayers(
      overlay,
      layers,
      handleTilesetLoad,
      getAuthTokenRef.current,
      getCoreUrlRef.current,
    );
  }, [layersKey, handleTilesetLoad, handlePopup]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoadedRef.current) return;
    applyTerrain(map, config.terrain);
  }, [config.terrain]);

  useImperativeHandle(
    ref,
    () => ({
      flyTo: (opts, instant) => {
        // maplibre-gl v6 regression, confirmed by e2e (with vs. without
        // terrain, with `flyTo` vs. `easeTo` vs. `jumpTo` — only the
        // animated forms fail, only when a terrain is currently set): an
        // animated pitch transition (`flyTo`/`easeTo`) while `map.getTerrain()`
        // is non-null lands the camera near pitch≈0 instead of the
        // requested value, regardless of target — repeatable, not a race.
        // `jumpTo` (no animation, no curve/elevation sampling) is
        // unaffected, so it's the fallback exactly when terrain is active;
        // `flyTo`'s scenic arc stays the default the rest of the time
        // (searched-location and explorer navigation, the other two
        // MapViewHandle.flyTo call sites, never touch terrain state).
        //
        // D42 (Vague C, SP-C2) : même bascule vers jumpTo, motif différent
        // — un visiteur ayant activé prefers-reduced-motion ne doit jamais
        // recevoir l'arc animé de flyTo. Interrogé à chaque appel (jamais
        // mis en cache dans un state/ref) : un changement de préférence
        // système en cours de session doit être respecté au prochain
        // flyTo, pas seulement à celui qui suit le montage.
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (instant || mapRef.current?.getTerrain() || reducedMotion) {
          mapRef.current?.jumpTo(opts);
        } else {
          mapRef.current?.flyTo(opts);
        }
      },
      highlight: (geometry) => {
        const src = mapRef.current?.getSource(HIGHLIGHT_ID) as
          { setData?: (d: unknown) => void } | undefined;
        src?.setData?.(
          geometry
            ? { type: "Feature", geometry, properties: {} }
            : { type: "FeatureCollection", features: [] },
        );
      },
      fitBounds: (bbox, opts) => {
        mapRef.current?.fitBounds(
          [
            [bbox[0], bbox[1]],
            [bbox[2], bbox[3]],
          ],
          opts,
        );
      },
    }),
    [],
  );

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map-container" />
      {!hideLegend && <MapLegend layers={config.layers} />}
      {popup && popupPoint && !toolsActive && (
        <MapPopup
          content={resolvePopupContent(popupConfig, popup.properties, popupSchema)}
          x={popupPoint.x}
          y={popupPoint.y}
          onClose={() => setPopup(null)}
          attachments={popupAttachments}
          onDownloadAttachment={(attachmentId, filename) =>
            void downloadPopupAttachment(attachmentId, filename)
          }
        />
      )}
      {interactiveTools && readyMap && (
        <MapMeasureSketchToolbar map={readyMap} onActiveChange={setToolsActive} />
      )}
    </div>
  );
});
