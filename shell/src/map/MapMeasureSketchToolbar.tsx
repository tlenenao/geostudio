// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import {
  formatArea,
  formatDistance,
  lineDistanceMeters,
  shapeToGeoJSONFeature,
  sphericalPolygonAreaSquareMeters,
  type LngLat,
  type SketchShape,
} from "./measureSketch";

export type ToolbarMode = "idle" | "measure-distance" | "measure-area" | "sketch";

const SKETCH_SOURCE_ID = "__sketch__";
const SKETCH_LAYER_IDS = [
  `${SKETCH_SOURCE_ID}line`,
  `${SKETCH_SOURCE_ID}fill`,
  `${SKETCH_SOURCE_ID}point`,
  // QUATRIÈME couche : le TEXTE des annotations. Constat I13 (Important) du
  // 2026-08-28 — sans elle, `shapeToGeoJSONFeature` produit bien un Point
  // portant `properties.text` pour `kind: "text"`, mais aucune couche ne le
  // dessine : sur la carte une annotation texte n'apparaît que comme un point
  // de 5 px, et le texte n'est lisible que dans la liste de la barre d'outils.
  // Le chantier 4.5 demande explicitement le croquis « texte » ; ce trou
  // n'était signalé NULLE PART (ni en déviation, ni en suivi), alors que la
  // dépendance `glyphs` qui l'explique est, elle, traitée explicitement pour
  // les étiquettes (Task 14).
  `${SKETCH_SOURCE_ID}text`,
] as const;

type SketchTool = "freehand" | "rect" | "circle" | "polygon" | "text" | null;

// Singulier / pluriel par type de forme : la version précédente ne rendait
// QUE les tracés libres, au singulier codé en dur — rectangles, cercles et
// polygones n'avaient aucun retour visuel.
const SHAPE_LABELS: Record<SketchShape["kind"], [string, string]> = {
  freehand: ["tracé", "tracés"],
  rect: ["rectangle", "rectangles"],
  circle: ["cercle", "cercles"],
  polygon: ["polygone", "polygones"],
  text: ["texte", "textes"],
};
const SHAPE_ORDER: SketchShape["kind"][] = ["freehand", "rect", "circle", "polygon", "text"];

// Purement client, éphémère : aucune dépendance ItemClient/fetch, par
// construction (spec §2 : jamais persisté, jamais envoyé au serveur). Ne pas
// ajouter de prop qui en introduirait une.
export type MapMeasureSketchToolbarMap = Pick<
  maplibregl.Map,
  | "on"
  | "off"
  | "getCanvas"
  | "getStyle"
  | "getSource"
  | "addSource"
  | "addLayer"
  | "getLayer"
  | "removeLayer"
  | "removeSource"
  | "isStyleLoaded"
>;

export function MapMeasureSketchToolbar({
  map,
  onActiveChange,
}: {
  map: MapMeasureSketchToolbarMap;
  // Prévient l'hôte qu'un mode mesure/croquis est actif, pour qu'il suspende
  // ses propres interactions (popups). Optionnel : les tests unitaires de
  // cette tâche rendent le composant sans lui.
  onActiveChange?: (active: boolean) => void;
}) {
  const [mode, setMode] = useState<ToolbarMode>("idle");
  const [points, setPoints] = useState<LngLat[]>([]);
  const [sketchTool, setSketchTool] = useState<SketchTool>(null);
  const [shapes, setShapes] = useState<SketchShape[]>([]);
  const [color, setColor] = useState("#dc2626");
  // Aperçu du tracé libre en cours : lu par l'effet de synchronisation de
  // Task 18 ci-dessous, pour que le geste soit visible sur la carte avant
  // `mouseup`.
  const [freehandPoints, setFreehandPoints] = useState<LngLat[]>([]);
  const [polygonPoints, setPolygonPoints] = useState<LngLat[]>([]);
  const drawingRef = useRef(false);
  // Coin en attente d'un rectangle/cercle : une REF, pas un état lu depuis un
  // updater. Un effet de bord dans un updater est exécuté deux fois sous
  // <StrictMode> (shell/src/main.tsx), ce qui ajouterait la forme deux fois.
  const pendingCornerRef = useRef<LngLat | null>(null);
  const [pendingCorner, setPendingCorner] = useState<LngLat | null>(null);
  // Points du tracé libre en cours : la REF est la source de vérité lue par
  // `mouseup`, l'ÉTAT ne sert qu'au rendu (l'aperçu de Task 18). C'est ce qui
  // permet à `mouseup` de ne faire que deux appels de setter ordinaires, sans
  // aucun effet de bord dans un updater.
  const freehandRef = useRef<LngLat[]>([]);
  // `map.on` n'est enregistré qu'une fois (dépendance [map]) mais le handler
  // doit voir l'état courant : une ref, tenue à jour DANS UN EFFET.
  //
  // Constat I9 (Important) du 2026-08-28 : la version précédente écrivait
  // `modeRef.current = mode;` **pendant le rendu** en invoquant « un patron
  // déjà utilisé ailleurs dans MapView ». Mesuré : `MapView.tsx` ne mute
  // JAMAIS une ref pendant le rendu — ses trois refs de props sont assignées
  // dans un `useEffect` (lignes 555-567 : onViewChange, onFeatureClick,
  // onReady, getAuthToken, getCoreUrl, layers, terrain), et les autres
  // (`mapRef`, `styleLoadedRef`) dans l'effet de montage. Le patron invoqué
  // n'existait pas — et c'est précisément celui que la correction 2.16
  // demandait de remplacer par « une ref + effet » en Task 12.
  const modeRef = useRef(mode);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);
  // Refs de props/état lues par des handlers enregistrés une seule fois. Mises
  // à jour DANS UN EFFET, jamais pendant le rendu (même patron que modeRef
  // ci-dessus, constat I9 de Task 12) : aucun précédent dans ce fichier de
  // mutation de ref au rendu.
  const sketchToolRef = useRef(sketchTool);
  useEffect(() => {
    sketchToolRef.current = sketchTool;
  }, [sketchTool]);
  const colorRef = useRef(color);
  useEffect(() => {
    colorRef.current = color;
  }, [color]);

  // Posé au montage, retiré au démontage. `isStyleLoaded()` est la garde
  // réelle : addSource/addLayer avant le chargement du style lèvent
  // « Style is not done loading. ». Tester l'existence de la MÉTHODE
  // getSource ne prouve rien (elle existe toujours) : la garde ci-dessous
  // teste la présence de la SOURCE elle-même.
  useEffect(() => {
    if (!map.isStyleLoaded()) return;
    if (map.getSource(SKETCH_SOURCE_ID)) return;
    map.addSource(SKETCH_SOURCE_ID, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: SKETCH_LAYER_IDS[0],
      type: "line",
      source: SKETCH_SOURCE_ID,
      filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": ["get", "color"], "line-width": 2 },
    } as never);
    map.addLayer({
      id: SKETCH_LAYER_IDS[1],
      type: "fill",
      source: SKETCH_SOURCE_ID,
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": ["get", "color"], "fill-opacity": 0.3 },
    } as never);
    map.addLayer({
      id: SKETCH_LAYER_IDS[2],
      type: "circle",
      source: SKETCH_SOURCE_ID,
      filter: ["==", ["geometry-type"], "Point"],
      paint: { "circle-color": ["get", "color"], "circle-radius": 5 },
    } as never);
    // Couche de TEXTE (constat I13). `text-field` exige que le STYLE déclare
    // `glyphs` — même contrainte que les étiquettes de Task 14, et même
    // traitement : sans glyphs on ne pose PAS la couche et on avertit une
    // fois, au lieu de la laisser rejeter en silence par le validateur.
    // (Constat Mineur 9 : la garde `if (!source?.setData) return;` de l'effet
    // de synchronisation ci-dessous avale silencieusement une source absente,
    // là où la branche jumelle de Task 14 fait console.warn — garde posée sur
    // une surface et pas sur sa jumelle. Ici les deux avertissent.)
    const style = map.getStyle() as { glyphs?: string } | undefined;
    if (style?.glyphs) {
      map.addLayer({
        id: SKETCH_LAYER_IDS[3],
        type: "symbol",
        source: SKETCH_SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        // Pas de `text-font` : le défaut du style-spec est
        // ["Open Sans Regular", "Arial Unicode MS Regular"], et nommer une
        // police absente du jeu de glyphes est un échec silencieux (Task 14).
        layout: {
          "text-field": ["get", "text"],
          "text-size": 12,
          "text-anchor": "top",
          "text-offset": [0, 0.6],
        },
        paint: {
          "text-color": ["get", "color"],
          "text-halo-color": "#ffffff",
          "text-halo-width": 1,
        },
      } as never);
    } else {
      console.warn(
        'MapMeasureSketchToolbar: texte de croquis non rendu sur la carte — le style du fond de carte ne déclare pas de "glyphs" (text-field l\'exige). Les formes et les mesures restent affichées.',
      );
    }
    return () => {
      // Les couches d'abord : MapLibre refuse de retirer une source encore
      // référencée (même règle que les deux passes d'applyLayers). Le
      // `getLayer` couvre le cas où la couche de texte n'a pas été posée
      // (style sans glyphs).
      for (const id of SKETCH_LAYER_IDS) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(SKETCH_SOURCE_ID)) map.removeSource(SKETCH_SOURCE_ID);
    };
  }, [map]);

  // Synchronise la source GeoJSON `__sketch__` avec l'état : les formes déjà
  // enregistrées, ET les tracés/formes en cours (mesure, tracé libre,
  // polygone en construction) — le retour visuel doit être visible avant la
  // fin du geste. Le polygone en cours est dessiné en LineString OUVERTE
  // volontairement : un anneau à moitié tracé rendu en polygone REMPLI
  // clignoterait à chaque clic.
  useEffect(() => {
    const source = map.getSource(SKETCH_SOURCE_ID) as
      { setData?: (d: unknown) => void } | undefined;
    // Retour silencieux ASSUMÉ ici (constat Mineur 9) : la seule façon
    // d'arriver là sans source est un style non chargé au montage, cas où
    // l'effet de montage n'a rien posé. L'avertissement appartient donc à
    // l'effet de montage, qui le fait, et non à cet effet, qui s'exécute à
    // chaque changement d'état et noierait la console.
    if (!source?.setData) return;
    const inProgress =
      points.length >= 2
        ? [
            shapeToGeoJSONFeature(
              mode === "measure-area"
                ? { kind: "polygon", points, color: colorRef.current }
                : { kind: "freehand", points, color: colorRef.current },
            ),
          ]
        : [];
    const drawing =
      freehandPoints.length >= 2
        ? [
            shapeToGeoJSONFeature({
              kind: "freehand",
              points: freehandPoints,
              color: colorRef.current,
            }),
          ]
        : [];
    const pendingPolygon =
      polygonPoints.length >= 2
        ? [
            shapeToGeoJSONFeature({
              kind: "freehand",
              points: polygonPoints,
              color: colorRef.current,
            }),
          ]
        : [];
    source.setData({
      type: "FeatureCollection",
      features: [
        ...shapes.map(shapeToGeoJSONFeature),
        ...inProgress,
        ...drawing,
        ...pendingPolygon,
      ],
    });
  }, [map, shapes, points, mode, freehandPoints, polygonPoints]);

  // Le mode actif change le curseur : c'est le seul retour visuel qui dit à
  // l'utilisateur que son prochain clic sera capté par la barre et non par la
  // carte. `getCanvas` est dans le Pick ci-dessus et n'avait AUCUN
  // utilisateur avant cette correction (constat I16).
  useEffect(() => {
    const canvas = map.getCanvas();
    const previous = canvas.style.cursor;
    canvas.style.cursor = mode === "idle" ? previous : "crosshair";
    return () => {
      canvas.style.cursor = previous;
    };
  }, [map, mode]);

  // Exclusivité vis-à-vis des interactions existantes de la carte (constat
  // I16) : `applyLayers` enregistre `map.on("click", layerId, handler)` par
  // couche et `MapPopup` est monté sur `{popup && popupPoint && …}`
  // (`MapView.tsx:817`), donc un clic de mesure sur une entité ouvrirait AUSSI
  // la popup — laquelle est en `z-20` (`MapPopup.tsx:34`) contre `z-10` pour
  // cette barre, et recouvrirait le texte même que les preuves E2E 4.5 de
  // Task 20 asserteront. On prévient l'hôte du mode actif ; MapView suspend
  // ses popups tant qu'il ne vaut pas "idle".
  useEffect(() => {
    onActiveChange?.(mode !== "idle");
  }, [mode, onActiveChange]);

  useEffect(() => {
    function onClick(e: unknown) {
      const { lngLat } = e as { lngLat: LngLat };
      const current = modeRef.current;
      if (current === "measure-distance" || current === "measure-area") {
        setPoints((prev) => [...prev, lngLat]);
        return;
      }
      if (current !== "sketch") return;
      const tool = sketchToolRef.current;
      if (tool === "text") {
        const text = window.prompt("Texte du marqueur :");
        if (text)
          setShapes((s) => [...s, { kind: "text", at: lngLat, text, color: colorRef.current }]);
        return;
      }
      if (tool === "rect" || tool === "circle") {
        const previous = pendingCornerRef.current;
        if (!previous) {
          pendingCornerRef.current = lngLat;
          setPendingCorner(lngLat);
          return;
        }
        pendingCornerRef.current = null;
        setPendingCorner(null);
        setShapes((s) => [
          ...s,
          tool === "rect"
            ? { kind: "rect", from: previous, to: lngLat, color: colorRef.current }
            : { kind: "circle", center: previous, edge: lngLat, color: colorRef.current },
        ]);
        return;
      }
      if (tool === "polygon") setPolygonPoints((prev) => [...prev, lngLat]);
    }
    map.on("click", onClick as never);
    return () => {
      map.off("click", onClick as never);
    };
  }, [map]);

  // Un SECOND effet, car il enregistre trois autres écouteurs
  // (mousedown/mousemove/mouseup) — le tracé libre est un geste continu, pas
  // un clic ponctuel.
  useEffect(() => {
    function onMouseDown(e: unknown) {
      if (modeRef.current !== "sketch" || sketchToolRef.current !== "freehand") return;
      drawingRef.current = true;
      const start = [(e as { lngLat: LngLat }).lngLat];
      // La REF est la source de vérité lue par mouseup ; l'état ne sert qu'au
      // rendu de l'aperçu (Task 18). Les deux sont écrits, jamais lus l'un
      // depuis l'updater de l'autre.
      freehandRef.current = start;
      setFreehandPoints(start);
    }
    function onMouseMove(e: unknown) {
      if (!drawingRef.current) return;
      const next = [...freehandRef.current, (e as { lngLat: LngLat }).lngLat];
      freehandRef.current = next;
      setFreehandPoints(next);
    }
    function onMouseUp() {
      if (!drawingRef.current) return;
      drawingRef.current = false;
      // On LIT la ref, puis on appelle les deux setters comme deux appels
      // ordinaires. Aucun effet de bord dans un updater, donc rien à
      // dédoubler sous <StrictMode>, et l'enregistrement est visible
      // SYNCHRONIQUEMENT par les tests du Step 1.
      const captured = freehandRef.current;
      freehandRef.current = [];
      setFreehandPoints([]);
      if (captured.length >= 2) {
        setShapes((s) => [...s, { kind: "freehand", points: captured, color: colorRef.current }]);
      }
    }
    map.on("mousedown", onMouseDown as never);
    map.on("mousemove", onMouseMove as never);
    map.on("mouseup", onMouseUp as never);
    return () => {
      map.off("mousedown", onMouseDown as never);
      map.off("mousemove", onMouseMove as never);
      map.off("mouseup", onMouseUp as never);
    };
  }, [map]);

  function startMode(next: ToolbarMode) {
    setMode(next);
    setPoints([]);
    // Fix M7 de la revue finale SP-27 : passer d'un mode "sketch" mi-tracé à
    // un autre mode (Mesurer/Surface) ne réinitialisait ni le polygone en
    // cours d'accumulation ni le coin en attente d'un rectangle/cercle — leur
    // résumé (le bloc "Terminer le polygone" / "Cliquez le second point…"
    // ci-dessous, tout comme leur tracé dans la source `__sketch__` via
    // l'effet de synchronisation) n'est conditionné à AUCUN endroit sur
    // `mode === "sketch"`, seulement sur `sketchTool`/`polygonPoints`/
    // `pendingCorner` eux-mêmes. Un polygone ou un rectangle à moitié tracé
    // restait donc visible sur la carte et dans la barre après avoir changé
    // d'outil vers "Mesurer"/"Surface". Le bouton de changement d'OUTIL de
    // croquis (plus bas, Tracé libre/Rectangle/Cercle/Polygone/Texte) fait
    // déjà ce nettoyage pour switcher d'outil SANS quitter le mode croquis ;
    // ceci est le même nettoyage pour switcher de MODE.
    setPolygonPoints([]);
    pendingCornerRef.current = null;
    setPendingCorner(null);
  }

  function clearAll() {
    setMode("idle");
    setPoints([]);
    setShapes([]);
    setSketchTool(null);
    // Fix M2 de la revue finale SP-27 : MapLibre ne déclenche pas `mouseup`
    // quand le bouton de la souris est relâché en dehors du canvas — le
    // tracé libre restait alors indéfiniment en mode « en cours » côté
    // `drawingRef` (jamais remis à `false` par cette fonction), et tout
    // `mousemove` suivant continuait d'accumuler des points sans qu'aucun
    // bouton ne soit réellement tenu enfoncé. « Effacer tout » est le geste
    // naturel d'un utilisateur bloqué dans cet état — il doit donc aussi
    // réinitialiser l'état de dessin, pas seulement les points accumulés.
    drawingRef.current = false;
    freehandRef.current = [];
    setFreehandPoints([]);
    setPolygonPoints([]);
    pendingCornerRef.current = null;
    setPendingCorner(null);
  }

  const distance =
    mode === "measure-distance" && points.length >= 2 ? lineDistanceMeters(points) : null;
  const area =
    mode === "measure-area" && points.length >= 3 ? sphericalPolygonAreaSquareMeters(points) : null;

  const buttonCls = "rounded border border-slate-300 px-2 py-1";

  return (
    <div className="absolute left-2 top-2 z-10 flex flex-col gap-1 rounded-md bg-white/90 p-2 text-xs shadow">
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          className={buttonCls}
          aria-pressed={mode === "measure-distance"}
          onClick={() => startMode("measure-distance")}
        >
          Mesurer
        </button>
        <button
          type="button"
          className={buttonCls}
          aria-pressed={mode === "measure-area"}
          onClick={() => startMode("measure-area")}
        >
          Surface
        </button>
        <button type="button" className={buttonCls} onClick={clearAll}>
          Effacer tout
        </button>
      </div>
      {distance !== null && <p>{formatDistance(distance)}</p>}
      {area !== null && <p>{formatArea(area)}</p>}
      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          className={buttonCls}
          aria-pressed={mode === "sketch"}
          onClick={() => {
            setMode("sketch");
            setPoints([]);
          }}
        >
          Croquis
        </button>
        {mode === "sketch" && (
          <>
            {(
              [
                ["freehand", "Tracé libre"],
                ["rect", "Rectangle"],
                ["circle", "Cercle"],
                ["polygon", "Polygone"],
                ["text", "Texte"],
              ] as [Exclude<SketchTool, null>, string][]
            ).map(([tool, label]) => (
              <button
                key={tool}
                type="button"
                className={buttonCls}
                aria-pressed={sketchTool === tool}
                onClick={() => {
                  setSketchTool(tool);
                  pendingCornerRef.current = null;
                  setPendingCorner(null);
                  setPolygonPoints([]);
                }}
              >
                {label}
              </button>
            ))}
            <input
              aria-label="Couleur du croquis"
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
            />
          </>
        )}
      </div>
      {pendingCorner && <p className="text-slate-500">Cliquez le second point…</p>}
      {sketchTool === "polygon" && polygonPoints.length >= 3 && (
        <button
          type="button"
          className={buttonCls}
          onClick={() => {
            setShapes((s) => [
              ...s,
              { kind: "polygon", points: polygonPoints, color: colorRef.current },
            ]);
            setPolygonPoints([]);
          }}
        >
          Terminer le polygone
        </button>
      )}
      {shapes.length > 0 && (
        <ul>
          {SHAPE_ORDER.map((kind) => {
            const n = shapes.filter((s) => s.kind === kind).length;
            if (n === 0) return null;
            const [one, many] = SHAPE_LABELS[kind];
            return (
              <li key={kind}>
                {n} {n > 1 ? many : one}
              </li>
            );
          })}
        </ul>
      )}
      {shapes.map((s, i) => (s.kind === "text" ? <p key={`t${i}`}>{s.text}</p> : null))}
    </div>
  );
}
