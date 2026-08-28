// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import {
  formatArea,
  formatDistance,
  lineDistanceMeters,
  sphericalPolygonAreaSquareMeters,
  type LngLat,
} from "./measureSketch";

export type ToolbarMode = "idle" | "measure-distance" | "measure-area" | "sketch";

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
      const current = modeRef.current;
      if (current !== "measure-distance" && current !== "measure-area") return;
      const { lngLat } = e as { lngLat: LngLat };
      setPoints((prev) => [...prev, lngLat]);
    }
    map.on("click", onClick as never);
    return () => {
      map.off("click", onClick as never);
    };
  }, [map]);

  function startMode(next: ToolbarMode) {
    setMode(next);
    setPoints([]);
  }

  function clearAll() {
    setMode("idle");
    setPoints([]);
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
    </div>
  );
}
