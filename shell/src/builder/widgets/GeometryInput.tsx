// SPDX-License-Identifier: Apache-2.0
/* eslint-disable geostudio/panel-trigger-aria -- boutons d'action (ajout/retrait de sommet), aucun panneau en ligne */
// L8 : saisie de géométrie LigneString/Polygone dans le formulaire (sommets par GPS, par
// coordonnées, ou trace GPS échantillonnée). La saisie d'un Point reste dans form.tsx.
import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { Button } from "../../ui/kit/Button";

export type Position = [number, number];
export type GeometryIssue = "incomplete" | null;

/** Distance minimale entre deux points d'une trace GPS (m). */
export const TRACE_STEP_M = 5;
/** Au-delà, la précision d'un fix GPS est signalée comme faible (m). */
export const ACCURACY_WARN_M = 30;

export function lineKind(geometryType: string | null | undefined): "LineString" | "Polygon" | null {
  const base = (geometryType ?? "").replace(/^Multi/, "");
  return base === "LineString" || base === "Polygon" ? base : null;
}

/** Distance haversine en mètres. */
export function distanceM(a: Position, b: Position): number {
  const rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad;
  const dLon = (b[0] - a[0]) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371008.8 * Math.asin(Math.sqrt(h));
}

/** Géométrie GeoJSON des sommets ; promue en Multi* si la collection l'exige (REV-352). */
export function buildGeometry(
  geometryType: string,
  points: Position[],
): { geometry: unknown | null; issue: GeometryIssue } {
  const kind = lineKind(geometryType);
  if (!kind || points.length === 0) return { geometry: null, issue: null };
  const multi = geometryType.startsWith("Multi");
  if (kind === "LineString") {
    if (points.length < 2) return { geometry: null, issue: "incomplete" };
    return {
      geometry: multi
        ? { type: "MultiLineString", coordinates: [points] }
        : { type: "LineString", coordinates: points },
      issue: null,
    };
  }
  if (points.length < 3) return { geometry: null, issue: "incomplete" };
  const ring = [...points, points[0]];
  return {
    geometry: multi
      ? { type: "MultiPolygon", coordinates: [[ring]] }
      : { type: "Polygon", coordinates: [ring] },
    issue: null,
  };
}

/** Sommets éditables d'une géométrie chargée ; null si elle a plusieurs parties (conservée). */
export function pointsOf(geometry: unknown): Position[] | null {
  const g = geometry as { type?: string; coordinates?: unknown } | null | undefined;
  if (!g || !Array.isArray(g.coordinates)) return [];
  const asPos = (c: unknown) => c as Position[];
  switch (g.type) {
    case "LineString":
      return asPos(g.coordinates);
    case "Polygon": {
      const ring = asPos((g.coordinates as unknown[])[0] ?? []);
      return ring.slice(0, -1);
    }
    case "MultiLineString":
      return g.coordinates.length === 1 ? asPos(g.coordinates[0]) : null;
    case "MultiPolygon": {
      const polys = g.coordinates as unknown[][];
      if (polys.length !== 1 || polys[0].length !== 1) return null;
      return asPos(polys[0][0]).slice(0, -1);
    }
    default:
      return [];
  }
}

export function GeometryInput({
  geometryType,
  value,
  onChange,
}: {
  geometryType: string;
  value: unknown;
  onChange: (geometry: unknown | null, issue: GeometryIssue) => void;
}) {
  const kind = lineKind(geometryType);
  const initial = pointsOf(value);
  const [points, setPoints] = useState<Position[]>(initial ?? []);
  // Géométrie à plusieurs parties : conservée telle quelle tant qu'on ne l'a pas effacée.
  const [replaced, setReplaced] = useState(false);
  const locked = initial === null && !replaced;
  const [lon, setLon] = useState("");
  const [lat, setLat] = useState("");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [geoError, setGeoError] = useState(false);
  const [tracing, setTracing] = useState(false);
  const watchId = useRef<number | null>(null);
  // La trace accumule via une ref de la liste courante (les rappels GPS survivent aux rendus).
  const live = useRef<Position[]>(points);

  function commit(next: Position[]) {
    setPoints(next);
    live.current = next;
    const built = buildGeometry(geometryType, next);
    onChange(built.geometry, built.issue);
  }

  function stopTrace() {
    if (watchId.current !== null) navigator.geolocation?.clearWatch(watchId.current);
    watchId.current = null;
    setTracing(false);
  }
  useEffect(
    () => () => {
      if (watchId.current !== null) navigator.geolocation?.clearWatch(watchId.current);
    },
    [],
  );

  function fix(pos: GeolocationPosition, onlyIfFar: boolean) {
    const p: Position = [pos.coords.longitude, pos.coords.latitude];
    setAccuracy(typeof pos.coords.accuracy === "number" ? pos.coords.accuracy : null);
    const prev = live.current[live.current.length - 1];
    if (onlyIfFar && prev && distanceM(prev, p) < TRACE_STEP_M) return;
    commit([...live.current, p]);
  }

  function addMyPosition() {
    setGeoError(false);
    if (!navigator.geolocation) return setGeoError(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => fix(pos, false),
      () => setGeoError(true),
      {
        enableHighAccuracy: true,
        timeout: 15000,
      },
    );
  }

  function startTrace() {
    setGeoError(false);
    if (!navigator.geolocation) return setGeoError(true);
    setTracing(true);
    watchId.current = navigator.geolocation.watchPosition(
      (pos) => fix(pos, true),
      () => {
        setGeoError(true);
        stopTrace();
      },
      { enableHighAccuracy: true },
    );
  }

  function addTyped() {
    if (lon === "" || lat === "" || Number.isNaN(Number(lon)) || Number.isNaN(Number(lat))) return;
    commit([...points, [Number(lon), Number(lat)]]);
    setLon("");
    setLat("");
  }

  if (!kind) return null;
  const built = buildGeometry(geometryType, points);
  const incompleteMsg =
    built.issue === "incomplete"
      ? t(
          kind === "LineString"
            ? "widgetForm.geometryIncompleteLine"
            : "widgetForm.geometryIncompletePolygon",
        )
      : null;

  if (locked) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-xs text-ink-2">{t("widgetForm.geometryMultiPart")}</p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setReplaced(true);
            commit([]);
          }}
        >
          {t("widgetForm.geometryClear")}
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2" role="group" aria-label={t("widgetForm.geometryGroup")}>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={addMyPosition}>
          {t("widgetForm.geometryAddMyPosition")}
        </Button>
        {tracing ? (
          <Button type="button" variant="outline" onClick={stopTrace}>
            {t("widgetForm.geometryTraceStop")}
          </Button>
        ) : (
          <Button type="button" variant="outline" onClick={startTrace}>
            {t("widgetForm.geometryTraceStart")}
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={points.length === 0}
          onClick={() => commit(points.slice(0, -1))}
        >
          {t("widgetForm.geometryUndo")}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={points.length === 0}
          onClick={() => commit([])}
        >
          {t("widgetForm.geometryClear")}
        </Button>
      </div>
      <div className="flex items-end gap-2">
        <label className="flex flex-1 flex-col gap-1">
          {t("widgetForm.longitude")}
          <input
            type="number"
            step="any"
            className="h-9 rounded-md border border-rule px-2 text-sm"
            value={lon}
            onChange={(e) => setLon(e.target.value)}
          />
        </label>
        <label className="flex flex-1 flex-col gap-1">
          {t("widgetForm.latitude")}
          <input
            type="number"
            step="any"
            className="h-9 rounded-md border border-rule px-2 text-sm"
            value={lat}
            onChange={(e) => setLat(e.target.value)}
          />
        </label>
        <Button type="button" variant="outline" onClick={addTyped}>
          {t("widgetForm.geometryAddPoint")}
        </Button>
      </div>
      <p className="text-xs text-ink-2" aria-live="polite">
        {t("widgetForm.geometryPoints", { count: points.length })}
        {tracing ? ` — ${t("widgetForm.geometryTracing", { step: TRACE_STEP_M })}` : ""}
      </p>
      {accuracy !== null && (
        <p
          className={accuracy > ACCURACY_WARN_M ? "text-xs text-danger" : "text-xs text-ink-2"}
          role={accuracy > ACCURACY_WARN_M ? "alert" : undefined}
        >
          {t(accuracy > ACCURACY_WARN_M ? "widgetForm.accuracyWarning" : "widgetForm.accuracyOk", {
            meters: Math.round(accuracy),
          })}
        </p>
      )}
      {incompleteMsg && (
        <p role="alert" className="text-xs text-danger">
          {incompleteMsg}
        </p>
      )}
      {geoError && (
        <p role="alert" className="text-xs text-danger">
          {t("widgetForm.positionError")}
        </p>
      )}
    </div>
  );
}
