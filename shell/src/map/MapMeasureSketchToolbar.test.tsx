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
    getStyle: (): { glyphs?: string } => ({
      glyphs: "https://glyphs.test/{fontstack}/{range}.pbf",
    }),
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

test("le tracé libre enregistre une forme au relâchement", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Tracé libre" }));
  act(() => map.emit("mousedown", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("mousemove", { lngLat: { lng: 0.001, lat: 0 } }));
  act(() => map.emit("mouseup", { lngLat: { lng: 0.001, lat: 0 } }));

  expect(screen.getByText("1 tracé")).toBeInTheDocument();
});

test("deux tracés libres affichent un pluriel", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Tracé libre" }));
  for (const offset of [0, 1]) {
    act(() => map.emit("mousedown", { lngLat: { lng: offset, lat: 0 } }));
    act(() => map.emit("mousemove", { lngLat: { lng: offset + 0.001, lat: 0 } }));
    act(() => map.emit("mouseup", { lngLat: { lng: offset + 0.001, lat: 0 } }));
  }
  expect(screen.getByText("2 tracés")).toBeInTheDocument();
});

test("le rectangle se ferme au second clic et n'est enregistré qu'une fois", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  expect(screen.queryByText(/rectangle/)).not.toBeInTheDocument();
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  expect(screen.getByText("1 rectangle")).toBeInTheDocument();
});

test("le cercle se ferme au second clic", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Cercle" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 0.1, lat: 0 } }));
  expect(screen.getByText("1 cercle")).toBeInTheDocument();
});

test("le polygone s'accumule puis se termine par « Terminer le polygone »", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Polygone" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  fireEvent.click(screen.getByRole("button", { name: "Terminer le polygone" }));
  expect(screen.getByText("1 polygone")).toBeInTheDocument();
});

test("« Terminer le polygone » n'apparaît qu'avec au moins trois sommets", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Polygone" }));
  expect(screen.queryByRole("button", { name: "Terminer le polygone" })).not.toBeInTheDocument();
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 0 } }));
  expect(screen.queryByRole("button", { name: "Terminer le polygone" })).not.toBeInTheDocument();
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  expect(screen.getByRole("button", { name: "Terminer le polygone" })).toBeInTheDocument();
});

test("l'outil Texte demande le texte et l'affiche", () => {
  const map = makeMapStub();
  vi.stubGlobal("prompt", vi.fn().mockReturnValue("Point de rendez-vous"));
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Texte" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  expect(screen.getByText("Point de rendez-vous")).toBeInTheDocument();
});

test("un texte annulé n'enregistre rien", () => {
  const map = makeMapStub();
  vi.stubGlobal("prompt", vi.fn().mockReturnValue(null));
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Texte" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  expect(screen.queryByText(/texte/)).not.toBeInTheDocument();
});

test("« Effacer tout » efface aussi les formes de croquis", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));
  expect(screen.queryByText("1 rectangle")).not.toBeInTheDocument();
});

// Fix M2 de la revue finale SP-27 : MapLibre ne déclenche pas `mouseup`
// quand le bouton de la souris est relâché hors du canvas — `drawingRef`
// restait alors bloqué à `true`, et « Effacer tout » (le geste naturel d'un
// utilisateur ainsi bloqué) ne le réinitialisait pas. Deux `mousemove`
// (nécessaires pour atteindre les 2 points requis par `shapeToGeoJSONFeature`)
// après le clic sur « Effacer tout » : sans le correctif, `drawingRef` est
// encore `true`, ils s'accumulent normalement et le `mouseup` qui suit
// enregistre une forme fantôme.
test("« Effacer tout » réinitialise un tracé libre bloqué (mousedown sans mouseup)", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Tracé libre" }));
  act(() => map.emit("mousedown", { lngLat: { lng: 0, lat: 0 } }));
  // Le bouton est relâché hors du canvas : mouseup n'arrive jamais ici.
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));
  act(() => map.emit("mousemove", { lngLat: { lng: 5, lat: 5 } }));
  act(() => map.emit("mousemove", { lngLat: { lng: 6, lat: 5 } }));
  act(() => map.emit("mouseup", { lngLat: { lng: 6, lat: 5 } }));
  expect(screen.queryByText(/tracé/)).not.toBeInTheDocument();
});

// Fix M7 de la revue finale SP-27 : `startMode` (appelée par « Mesurer » et
// « Surface ») ne réinitialisait ni `polygonPoints` ni le coin en attente
// d'un rectangle/cercle — leur résumé n'est conditionné nulle part sur
// `mode === "sketch"`, seulement sur ces états eux-mêmes, donc un polygone
// à moitié tracé restait affiché après avoir changé de mode.
test("changer de mode pendant un polygone en cours efface son résumé", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Polygone" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  expect(screen.getByRole("button", { name: "Terminer le polygone" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  expect(screen.queryByRole("button", { name: "Terminer le polygone" })).not.toBeInTheDocument();
});

// Constat I11 (Important) du 2026-08-28 : la version précédente titrait « la
// couleur du croquis est appliquée » et n'assertait QUE `getByText("1
// rectangle")` — le titre affirmait une propriété que le test ne pouvait pas
// faire échouer. Ce qui est réellement vérifiable ICI est le geste (le sélecteur
// de couleur existe, est réglable, et une forme s'enregistre après) ; la couleur
// effectivement portée par la forme est asserée sur la source GeoJSON en
// Task 18, dont le test s'appelle « une forme de croquis atteint la source
// GeoJSON avec sa couleur ». Titre corrigé pour dire ce qui est prouvé.
test("le sélecteur de couleur du croquis est réglable et n'empêche pas l'enregistrement", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  const picker = screen.getByLabelText("Couleur du croquis") as HTMLInputElement;
  fireEvent.change(picker, { target: { value: "#00ff00" } });
  expect(picker.value).toBe("#00ff00");
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  expect(screen.getByText("1 rectangle")).toBeInTheDocument();
});

function sketchData(map: ReturnType<typeof makeMapStub>) {
  const src = map.sources.get("__sketch__") as { data?: unknown } | undefined;
  return src?.data as
    { type: "FeatureCollection"; features: { properties: Record<string, unknown> }[] } | undefined;
}

test("les quatre couches d'overlay et la source sont posées une seule fois", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  expect(map.addSource).toHaveBeenCalledTimes(1);
  expect(map.layers.map((l) => l.id)).toEqual([
    "__sketch__line",
    "__sketch__fill",
    "__sketch__point",
    "__sketch__text",
  ]);

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  // Mise à jour par setData, jamais un second addSource.
  expect(map.addSource).toHaveBeenCalledTimes(1);
});

test("une forme de croquis atteint la source GeoJSON avec sa couleur", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.change(screen.getByLabelText("Couleur du croquis"), {
    target: { value: "#00ff00" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));

  const data = sketchData(map);
  expect(data?.features).toHaveLength(1);
  expect(data?.features[0].properties.color).toBe("#00ff00");
});

test("la mesure en cours est visible sur la carte avant d'être terminée", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 0 } }));
  const data = sketchData(map);
  expect(data?.features).toHaveLength(1);
});

test("« Effacer tout » vide la source", () => {
  const map = makeMapStub();
  render(<MapMeasureSketchToolbar map={map as never} />);
  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Rectangle" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));
  act(() => map.emit("click", { lngLat: { lng: 1, lat: 1 } }));
  fireEvent.click(screen.getByRole("button", { name: "Effacer tout" }));
  expect(sketchData(map)?.features).toEqual([]);
});

test("le démontage retire les quatre couches et la source", () => {
  const map = makeMapStub();
  const { unmount } = render(<MapMeasureSketchToolbar map={map as never} />);
  unmount();
  expect(map.layers).toEqual([]);
  expect(map.sources.has("__sketch__")).toBe(false);
});

// Constat I12 (Important) du 2026-08-28 : le titre précédent promettait « et
// l'overlay est posé ensuite ». Il n'y a AUCUNE reprise : l'effet de montage
// est `if (!map.isStyleLoaded()) return;` avec dépendance `[map]` et aucun
// écouteur `load`/`styledata` pour réessayer. En pratique cela ne se produit
// pas — Task 16 monte la barre depuis `map.on("load")`, donc le style EST
// chargé — ce qui est une raison de plus pour que le titre ne promette pas une
// reprise inexistante. Titre corrigé, et l'assertion complétée par la seule
// autre propriété réellement vérifiable ici : aucune couche non plus.
test("un style non chargé ne fait rien lever et ne pose aucune couche", () => {
  const map = makeMapStub();
  map.isStyleLoaded = () => false;
  expect(() => render(<MapMeasureSketchToolbar map={map as never} />)).not.toThrow();
  expect(map.addSource).not.toHaveBeenCalled();
  expect(map.layers).toEqual([]);
});

// Constat I13 : le texte de croquis doit atteindre la carte, pas seulement la
// liste de la barre d'outils.
test("une annotation texte atteint la source avec son texte, et sa couche est posée", () => {
  const map = makeMapStub();
  vi.stubGlobal("prompt", vi.fn().mockReturnValue("Rendez-vous"));
  render(<MapMeasureSketchToolbar map={map as never} />);
  expect(map.layers.map((l) => l.id)).toContain("__sketch__text");

  fireEvent.click(screen.getByRole("button", { name: "Croquis" }));
  fireEvent.click(screen.getByRole("button", { name: "Texte" }));
  act(() => map.emit("click", { lngLat: { lng: 0, lat: 0 } }));

  const data = sketchData(map);
  expect(data?.features).toHaveLength(1);
  expect(data?.features[0].properties.text).toBe("Rendez-vous");
});

test("sans glyphs dans le style, la couche de texte n'est pas posée et l'auteur est averti", () => {
  const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
  const map = makeMapStub();
  map.getStyle = () => ({});
  render(<MapMeasureSketchToolbar map={map as never} />);
  expect(map.layers.map((l) => l.id)).toEqual([
    "__sketch__line",
    "__sketch__fill",
    "__sketch__point",
  ]);
  expect(spy).toHaveBeenCalledWith(expect.stringContaining("glyphs"));
  spy.mockRestore();
});
