// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import {
  formatArea,
  formatDistance,
  lineDistanceMeters,
  sphericalPolygonAreaSquareMeters,
  type LngLat,
  type SketchShape,
} from "./measureSketch";

export type ToolbarMode = "idle" | "measure-distance" | "measure-area" | "sketch";

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
  // La valeur lue (`_freehandPoints`) n'a pas encore de consommateur : elle
  // sert à l'aperçu du tracé en cours, rendu par Task 18. Préfixe `_` = la
  // convention déjà en usage dans ce dépôt pour un `no-unused-vars`
  // délibéré (cf. `eslint.config.js`), pas une valeur au rebut.
  const [_freehandPoints, setFreehandPoints] = useState<LngLat[]>([]);
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
  }

  function clearAll() {
    setMode("idle");
    setPoints([]);
    setShapes([]);
    setSketchTool(null);
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
