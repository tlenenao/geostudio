// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { t } from "../i18n";
import { LayersPanel } from "./LayersPanel";
import { publishViewport } from "./viewportTiles";

// P30.03 : le client de test relaie fetchUrl vers le `fetch` global stubbé ; les
// options (`authenticated`) sont transmises telles quelles pour être assertées.
const fetchUrl = (url: string, opts?: unknown) => fetch(url, opts as RequestInit);

// LayersPanel est un composant contrôlé pur (comme PopupEditor/
// LayerPopupEditor) : sans état local qui répercute onChange dans layers,
// React réinitialise à chaque frappe la valeur affichée d'un <input>
// contrôlé (mécanisme documenté de restauration de valeur — cf. le vi.fn()
// nu de renderPanel, qui suffit pour les tests à interaction unique du
// fichier, mais pas ici). Le test ci-dessous enchaîne saisie → sélection →
// clic, donc a besoin d'un vrai aller-retour d'état, comme le ferait la
// vraie page hôte (draft.layers). Petit composant hôte local dédié à ce
// seul test.
function SymbologyHost({
  initialLayers,
  onLayersChange,
}: {
  initialLayers: MapLayer[];
  onLayersChange: (layers: MapLayer[]) => void;
}) {
  const [current, setCurrent] = useState(initialLayers);
  return (
    <LayersPanel
      layers={current}
      onChange={(next) => {
        setCurrent(next);
        onLayersChange(next);
      }}
    />
  );
}

const layers: MapLayer[] = [
  { id: "a", title: "A", visible: true, kind: "feature", url: "u1" },
  { id: "b", title: "B", visible: true, kind: "feature", url: "u2" },
];

// Chaque couche "feature" ci-dessus déclenche désormais un fetch de son
// `url` au montage (Task 2, SP-28) — sans repli, MSW (onUnhandledRequest:
// "error", src/test/setup.ts) ferait échouer tout test de ce fichier qui
// n'attend rien de particulier de cette requête. Un rejet par défaut
// reproduit exactement le comportement d'avant (availableFields=[]) pour
// les tests qui ne testent pas la symbologie feature elle-même.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not mocked in this test")));
});
afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPanel(current: MapLayer[], onChange: (l: MapLayer[]) => void) {
  const client = {
    fetchUrl,
    listLayerSources: vi.fn().mockResolvedValue([]),
    getCollectionSchema: vi.fn().mockResolvedValue({ fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayersPanel layers={current} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("toggles a layer's visibility", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Masquer A" }));
  expect(onChange).toHaveBeenCalledWith([{ ...layers[0], visible: false }, layers[1]]);
});

test("removes a layer", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Retirer A" }));
  expect(onChange).toHaveBeenCalledWith([layers[1]]);
});

test("moves a layer down", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Descendre A" }));
  expect(onChange).toHaveBeenCalledWith([layers[1], layers[0]]);
});

test("the layers panel exposes the popup editor of each layer", async () => {
  const onChange = vi.fn();
  const vectorLayer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "u",
    sourceLayer: "communes",
    collectionId: "communes",
  };
  renderPanel([vectorLayer], onChange);
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ popup: {} })]);
});

test("a vector layer with a collectionId exposes the symbology editor and can recompute a numeric domain", async () => {
  const onChange = vi.fn();
  const client = {
    fetchUrl,
    listLayerSources: vi.fn().mockResolvedValue([]),
    getCollectionSchema: vi.fn().mockResolvedValue({ fields: [{ name: "pop" }] }),
    queryDataSource: vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]),
    sampleCollectionField: vi.fn(),
  } as unknown as ItemClient;
  const vectorLayer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "u",
    sourceLayer: "communes",
    collectionId: "communes",
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <SymbologyHost initialLayers={[vectorLayer]} onLayersChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await userEvent.type(screen.getByLabelText("Champ couleur"), "pop");
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(client.queryDataSource).toHaveBeenCalledWith(
    expect.objectContaining({
      type: "statistics",
      service: "core",
      layer: "communes",
      query: expect.objectContaining({ measures: expect.any(Array) }),
    }),
  );
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({
      symbology: expect.objectContaining({
        color: expect.objectContaining({ domain: { kind: "numeric", min: 0, max: 100 } }),
      }),
    }),
  ]);
});

test("a raster layer has no popup editor", () => {
  const rasterLayer: MapLayer = {
    id: "r",
    title: "Fond",
    visible: true,
    kind: "raster",
    tilesUrl: "u",
  };
  renderPanel([rasterLayer], () => {});
  expect(
    screen.queryByRole("checkbox", { name: "Afficher les attributs au clic" }),
  ).not.toBeInTheDocument();
});

test("une couche raster expose un contrôle d'opacité (GAP-35)", () => {
  const rasterLayers: MapLayer[] = [
    { id: "r1", title: "Ortho", visible: true, kind: "raster", tilesUrl: "https://t", opacity: 1 },
  ];
  const onChange = vi.fn();
  renderPanel(rasterLayers, onChange);
  const slider = screen.getByRole("slider", { name: /opacité/i });
  fireEvent.change(slider, { target: { value: "0.4" } });
  expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ id: "r1", opacity: 0.4 })]);
});

test("un éditeur JSON avancé permet d'écrire layer.paint (GAP-45)", async () => {
  const vectorLayers: MapLayer[] = [
    {
      id: "v1",
      title: "V",
      visible: true,
      kind: "vector",
      tilesUrl: "https://t",
      sourceLayer: "s",
    },
  ];
  const onChange = vi.fn();
  renderPanel(vectorLayers, onChange);
  await userEvent.click(screen.getByRole("button", { name: /avancé/i, expanded: false }));
  const textarea = screen.getByRole("textbox", { name: /peinture maplibre/i });
  fireEvent.change(textarea, { target: { value: '{"fill-color":"#f00"}' } });
  fireEvent.blur(textarea);
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({ id: "v1", paint: { "fill-color": "#f00" } }),
  ]);
});

test("un JSON invalide affiche une erreur sans appeler onChange (GAP-45)", async () => {
  const vectorLayers: MapLayer[] = [
    {
      id: "v1",
      title: "V",
      visible: true,
      kind: "vector",
      tilesUrl: "https://t",
      sourceLayer: "s",
    },
  ];
  const onChange = vi.fn();
  renderPanel(vectorLayers, onChange);
  await userEvent.click(screen.getByRole("button", { name: /avancé/i, expanded: false }));
  const textarea = screen.getByRole("textbox", { name: /peinture maplibre/i });
  fireEvent.change(textarea, { target: { value: "{not json" } });
  fireEvent.blur(textarea);
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

test("une couche deck de type heatmap expose un contrôle de rayon en pixels (GAP-36)", () => {
  const deckLayers: MapLayer[] = [
    {
      id: "d1",
      title: "D",
      visible: true,
      kind: "deck",
      deckType: "heatmap",
      dataUrl: "https://d",
    },
  ];
  const onChange = vi.fn();
  renderPanel(deckLayers, onChange);
  fireEvent.change(screen.getByLabelText("Rayon (pixels)"), { target: { value: "40" } });
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({ id: "d1", props: expect.objectContaining({ radiusPixels: 40 }) }),
  ]);
});

test("une couche deck de type hexbin expose un contrôle de rayon en mètres (GAP-36)", () => {
  const deckLayers: MapLayer[] = [
    { id: "d1", title: "D", visible: true, kind: "deck", deckType: "hexbin", dataUrl: "https://d" },
  ];
  const onChange = vi.fn();
  renderPanel(deckLayers, onChange);
  fireEvent.change(screen.getByLabelText("Rayon (mètres)"), { target: { value: "500" } });
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({ id: "d1", props: expect.objectContaining({ radius: 500 }) }),
  ]);
});

test("une couche deck de type column expose un contrôle d'échelle de hauteur (GAP-36)", () => {
  const deckLayers: MapLayer[] = [
    { id: "d1", title: "D", visible: true, kind: "deck", deckType: "column", dataUrl: "https://d" },
  ];
  const onChange = vi.fn();
  renderPanel(deckLayers, onChange);
  fireEvent.change(screen.getByLabelText("Échelle de hauteur"), { target: { value: "3" } });
  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({
      id: "d1",
      props: expect.objectContaining({ elevationScale: 3 }),
    }),
  ]);
});

test("a feature layer without a collection lists fields from its fetched GeoJSON in the popup editor", async () => {
  const onChange = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: { nom: "A" }, geometry: null }],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fc }));
  const featureLayer: MapLayer = {
    id: "l1",
    title: "Points",
    visible: true,
    kind: "feature",
    url: "https://ex.test/points.geojson",
  };
  // SymbologyHost (voir le commentaire en tête de fichier), pas le
  // `renderPanel` nu utilisé par les autres tests de ce fichier : cocher la
  // case ne réapparaît dans le DOM que si `onChange` reboucle réellement
  // dans `layer.popup`, sans quoi React resynchronise la case décochée dès
  // le prochain rendu (celui déclenché par la résolution du fetch), avant
  // même que ce test ne puisse observer la case "nom" — écart trouvé en
  // exécutant ce test tel qu'écrit dans la brief avec `renderPanel`.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider
        client={
          { fetchUrl, listLayerSources: vi.fn().mockResolvedValue([]) } as unknown as ItemClient
        }
      >
        <SymbologyHost initialLayers={[featureLayer]} onLayersChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(await screen.findByRole("checkbox", { name: "nom" })).toBeInTheDocument();
});

test("a feature layer without a collection computes Jenks classes from its own GeoJSON", async () => {
  const onChange = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map((pop, i) => ({
      type: "Feature",
      properties: { pop },
      geometry: { type: "Point", coordinates: [i, i] },
    })),
  };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => fc });
  vi.stubGlobal("fetch", fetchMock);
  const featureLayer: MapLayer = {
    id: "l1",
    title: "Points",
    visible: true,
    kind: "feature",
    url: "https://ex.test/points.geojson",
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider
        client={
          { fetchUrl, listLayerSources: vi.fn().mockResolvedValue([]) } as unknown as ItemClient
        }
      >
        <SymbologyHost initialLayers={[featureLayer]} onLayersChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith("https://ex.test/points.geojson", {
      authenticated: false,
    }),
  );
  await userEvent.type(screen.getByLabelText("Champ couleur"), "pop");
  await userEvent.selectOptions(screen.getByLabelText("Type de couleur"), "numeric");
  await userEvent.selectOptions(screen.getByLabelText("Méthode de classification"), "jenks");
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({
      symbology: expect.objectContaining({
        color: expect.objectContaining({
          domain: expect.objectContaining({ kind: "numeric-classed" }),
        }),
      }),
    }),
  ]);
});

test("a feature layer whose GeoJSON fails to load still shows a symbology editor with no crash", async () => {
  const onChange = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
  const featureLayer: MapLayer = {
    id: "l1",
    title: "Points",
    visible: true,
    kind: "feature",
    url: "https://ex.test/points.geojson",
  };
  renderPanel([featureLayer], onChange);
  expect(await screen.findByLabelText("Champ couleur")).toHaveValue("");
});

// SP-B10c (Task 14) : MapLibre ne remonte pas les en-têtes de réponse au code
// applicatif pour une source `vector` déclarative — sonde ponctuelle sur la
// tuile racine (0/0/0.mvt) de chaque couche vecteur au montage, cf. brief.
const vectorLayer: MapLayer = {
  id: "l1",
  title: "Communes",
  visible: true,
  kind: "vector",
  tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
  sourceLayer: "communes",
  collectionId: "communes",
};

// `getAuthToken` : ItemClient partiel dédié à ces deux tests, pour vérifier
// que le jeton est bien propagé sur la requête de sonde (patron
// `?.()`/ItemClient partiel déjà suivi par le reste de ce fichier).
function renderPanelWithAuthToken(current: MapLayer[], onChange: (l: MapLayer[]) => void) {
  const client = {
    fetchUrl,
    listLayerSources: vi.fn().mockResolvedValue([]),
    getCollectionSchema: vi.fn().mockResolvedValue({ fields: [] }),
    getAuthToken: () => "mock-token",
    getCoreUrl: () => "https://core.test",
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayersPanel layers={current} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche un badge de troncature quand la tuile racine répond X-Tile-Truncated", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(new Uint8Array(), {
        status: 200,
        headers: { "X-Tile-Truncated": "true" },
      }),
    ),
  );
  renderPanelWithAuthToken([vectorLayer], vi.fn());
  expect(await screen.findByText(t("layersPanel.truncatedBadge"))).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("https://core.test/collections/communes/tiles/0/0/0.mvt", {
    authenticated: true,
  });
});

// Régression C2 (revue finale Vague B) : la sonde attachait le jeton OIDC à
// TOUTE couche vecteur, y compris une URL externe choisie par l'auteur de la
// carte — fuite du jeton de session vers une origine tierce.
test("n'attache le jeton qu'aux tuiles servies par le cœur, jamais à une origine tierce", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(() => Promise.resolve(new Response(new Uint8Array(), { status: 200 }))),
  );
  const externalLayer: MapLayer = {
    id: "l2",
    title: "Externe",
    visible: true,
    kind: "vector",
    tilesUrl: "https://attacker.example/collections/x/tiles/{z}/{x}/{y}.mvt",
    sourceLayer: "x",
  };
  renderPanelWithAuthToken([vectorLayer, externalLayer], vi.fn());
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  expect(fetch).toHaveBeenCalledWith("https://core.test/collections/communes/tiles/0/0/0.mvt", {
    authenticated: true,
  });
  // Tuile tierce : jamais sondée (ni jeton, ni requête).
  expect(fetch).not.toHaveBeenCalledWith(
    "https://attacker.example/collections/x/tiles/0/0/0.mvt",
    expect.anything(),
  );
});

test("n'affiche aucun badge quand la tuile n'est pas tronquée", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(new Uint8Array(), { status: 200 })),
  );
  renderPanelWithAuthToken([vectorLayer], vi.fn());
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(screen.queryByText(t("layersPanel.truncatedBadge"))).not.toBeInTheDocument();
});

// P29.06 (t03-010) : le badge suit les tuiles de la VUE, pas la seule 0/0/0.
// En dernier du fichier : le viewport publié est global au module.
test("sonde les tuiles visibles et le badge disparaît quand elles sont complètes", async () => {
  const truncatedRoot = (url: string) => url.endsWith("/0/0/0.mvt");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) =>
      Promise.resolve(
        new Response(new Uint8Array(), {
          status: 200,
          headers: truncatedRoot(url) ? { "X-Tile-Truncated": "true" } : {},
        }),
      ),
    ),
  );
  const { unmount } = renderPanelWithAuthToken([vectorLayer], vi.fn());
  expect(await screen.findByText(t("layersPanel.truncatedBadge"))).toBeInTheDocument();
  act(() => publishViewport({ zoom: 12.4, bounds: [2.34, 48.85, 2.36, 48.86] }));
  await waitFor(() =>
    expect(screen.queryByText(t("layersPanel.truncatedBadge"))).not.toBeInTheDocument(),
  );
  const urls = (fetch as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[0] as string);
  expect(urls.some((u) => /\/12\/\d+\/\d+\.mvt$/.test(u))).toBe(true);
  unmount();
});
