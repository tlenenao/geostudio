// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { LayersPanel } from "./LayersPanel";

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
        client={{ listLayerSources: vi.fn().mockResolvedValue([]) } as unknown as ItemClient}
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
        client={{ listLayerSources: vi.fn().mockResolvedValue([]) } as unknown as ItemClient}
      >
        <SymbologyHost initialLayers={[featureLayer]} onLayersChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );

  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("https://ex.test/points.geojson"));
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
