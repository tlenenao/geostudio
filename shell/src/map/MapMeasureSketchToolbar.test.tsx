// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { MapMeasureSketchToolbar } from "./MapMeasureSketchToolbar";

// Constat (2026-08-29, mesuré) : `map.emit(...)` invoque le handler
// directement — hors du système d'événements synthétiques de React, comme
// `fireOnLayer` dans MapView.test.tsx — donc le `setState` qu'il déclenche
// n'est pas garanti flush avant l'assertion suivante sous React 19 +
// `@testing-library/react` (racine concurrente). Un test isolé
// (`useState`+bouton hors `act`) confirme la manifestation : le texte reste à
// "0" tant que l'appel n'est pas enveloppé dans `act()`. Le brief pastait le
// code de `map.emit(...)` sans `act()` ; corrigé ici en appliquant le même
// patron que `MapView.test.tsx` (`act(() => mapInstances[0].fireOnLayer(...))`).

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeMapStub() {
  const handlers: Record<string, ((e: unknown) => void)[]> = {};
  const sources = new Map<string, unknown>();
  const layers: { id: string }[] = [];
  // Un SEUL objet canvas, pour que les tests puissent lire le curseur posé par
  // l'effet de mode.
  const canvas = { style: {} as Record<string, string> };
  return {
    canvas,
    on: vi.fn((event: string, handler: (e: unknown) => void) => {
      (handlers[event] ??= []).push(handler);
    }),
    off: vi.fn((event: string, handler: (e: unknown) => void) => {
      handlers[event] = (handlers[event] ?? []).filter((h) => h !== handler);
    }),
    emit: (event: string, e: unknown) => [...(handlers[event] ?? [])].forEach((h) => h(e)),
    handlerCount: (event: string) => (handlers[event] ?? []).length,
    getCanvas: () => canvas,
    // Task 18 pose une couche `symbol` pour le texte de croquis, qui exige que
    // le style déclare des `glyphs` : le stub en déclare, et un test le retire
    // pour couvrir la branche de refus.
    getStyle: () => ({ glyphs: "https://glyphs.test/{fontstack}/{range}.pbf" }),
    isStyleLoaded: () => true,
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string, spec: unknown) => {
      // `setData` MUTE l'objet source ; il ne le REMPLACE pas.
      //
      // Constat B5 (Bloquant) du 2026-08-28 : la version précédente faisait
      // `setData: (d) => sources.set(id, { data: d })`, ce qui remplaçait
      // l'objet par `{ data: d }` — sans méthode `setData`. Or l'effet de
      // synchronisation de Task 18 commence par `if (!source?.setData) return;`
      // et s'exécute une PREMIÈRE fois au montage (formes vides) : dès ce
      // premier appel la source devenait inerte. Simulé littéralement en Node :
      // `1st setData? function` / `2nd setData? undefined`. Conséquences
      // mesurées sur Task 18 : deux tests en échec (« une forme de croquis
      // atteint la source », « la mesure en cours est visible ») et un qui
      // PASSAIT pour la mauvaise raison (« Effacer tout vide la source »
      // attendait `[]` et obtenait `[]` alors que rien ne fonctionnait).
      const rec: { data?: unknown; setData: (d: unknown) => void; setDataCalls: number } = {
        ...(spec as object),
        setDataCalls: 0,
        setData: (d: unknown) => {
          rec.data = d;
          rec.setDataCalls += 1;
        },
      } as never;
      sources.set(id, rec);
    }),
    addLayer: vi.fn((layer: { id: string }) => layers.push(layer)),
    getLayer: vi.fn((id: string) => layers.find((l) => l.id === id)),
    removeLayer: vi.fn((id: string) => {
      const i = layers.findIndex((l) => l.id === id);
      if (i >= 0) layers.splice(i, 1);
    }),
    removeSource: vi.fn((id: string) => sources.delete(id)),
    sources,
    layers,
  };
}

test("« Mesurer » puis deux clics affichent la distance courante", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 0 } }));

  expect(screen.getByText("111,19 km")).toBeInTheDocument();
});

test("« Surface » puis trois clics affichent une surface", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Surface" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 0.01, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 0.01, lat: 0.01 } }));

  expect(screen.getByText(/ha|m²|km²/)).toBeInTheDocument();
});

test("« Effacer tout » efface la mesure courante", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 0 } }));
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));

  expect(screen.queryByText(/km$/)).not.toBeInTheDocument();
});

// Constat I10 (Important) du 2026-08-28 : la version précédente n'assertait
// que `queryByText(/km$/)`. Or l'affichage est de toute façon gardé côté rendu
// (`const distance = mode === "measure-distance" && points.length >= 2 ? …`),
// donc supprimer le garde du HANDLER laissait ce test vert : il ne mesurait pas
// la propriété qu'il nomme. On asserte donc une conséquence OBSERVABLE de
// l'absence de point : la source GeoJSON `__sketch__` (Task 18) reste vide.
// Cette assertion arrive donc avec Task 18 ; en Task 16, le test se limite à ce
// qu'il peut réellement prouver, et son titre le dit.
test("hors mode mesure, aucune distance n'est affichée après deux clics", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  map.emit("click", { lngLat: { lng: 0, lat: 0 } });
  map.emit("click", { lngLat: { lng: 1, lat: 0 } });
  expect(screen.queryByText(/km$/)).not.toBeInTheDocument();
  // Le mode reste "idle" : aucun bouton de mesure n'est enfoncé.
  expect(screen.getByRole("button", { name: "Mesurer" })).toHaveAttribute("aria-pressed", "false");
});

// Exigence de la spec §2 : jamais envoyé au serveur. Un test réel, pas une
// assertion sur Function.length (qui vaut 1 pour tout composant à objet de
// props et ne peut donc jamais échouer).
test("aucune requête réseau n'est émise par la barre d'outils", () => {
  const fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
  const xhrSpy = vi.fn();
  vi.stubGlobal(
    "XMLHttpRequest",
    class {
      open = xhrSpy;
      send = xhrSpy;
      setRequestHeader = () => {};
    },
  );
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 0 } }));
  fireEvent.click(screen.getByRole("button", { name: "Surface" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));

  expect(fetchSpy).not.toHaveBeenCalled();
  expect(xhrSpy).not.toHaveBeenCalled();
});

test("le démontage retire les écouteurs de la carte", () => {
  const map = makeMapStub();
  const { unmount } = render(<MapMeasureSketchToolbar map={map as never} />);
  expect(map.handlerCount("click")).toBe(1);
  unmount();
  expect(map.handlerCount("click")).toBe(0);
});
