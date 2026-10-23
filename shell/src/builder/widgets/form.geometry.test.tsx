// SPDX-License-Identifier: Apache-2.0
// L8 : saisie ligne/polygone/trace GPS, géométrie requise, précision.
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionSchema, ItemClient } from "../../api/types";
import type { WidgetContext } from "../registry";
import type { FormField } from "./form";
import { ActionBus } from "../ActionBus";
import { buildGeometry, distanceM, pointsOf } from "./GeometryInput";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});
afterEach(() => vi.unstubAllGlobals());

const nom: FormField = {
  name: "nom",
  type: "string",
  label: "Nom",
  order: 0,
  hidden: false,
  required: false,
};

function renderForm(
  geometryType: string,
  opts: {
    required?: boolean;
    mobile?: boolean;
    extraFields?: FormField[];
    client?: Partial<ItemClient>;
  } = {},
) {
  const schema: CollectionSchema = {
    collection: "c",
    pk: "id",
    geometry: {
      column: "geom",
      type: geometryType,
      srid: 4326,
      ...(opts.required ? { required: true } : {}),
    },
    fields: [],
  };
  const client = {
    createFeature: vi.fn().mockResolvedValue({ id: 1 }),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    getCollectionPermission: vi.fn().mockResolvedValue(true),
    ...opts.client,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{
            dataSourceId: "ds",
            fields: [nom, ...(opts.extraFields ?? [])],
            submitLabel: "Envoyer",
            geometryType,
            mobile: opts.mobile === true,
          }}
          ctx={
            {
              mode: "runtime",
              data: { loading: false, error: false, records: [], layer: "c" },
            } as WidgetContext
          }
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

async function addTyped(lon: string, lat: string) {
  await userEvent.type(screen.getByLabelText("Longitude"), lon);
  await userEvent.type(screen.getByLabelText("Latitude"), lat);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter ce point" }));
}

const sent = (c: ItemClient) => (c.createFeature as ReturnType<typeof vi.fn>).mock.calls[0][1];

test("buildGeometry : ligne >= 2 points, polygone refermé >= 3, promotion Multi", () => {
  const a: [number, number] = [0, 0];
  const b: [number, number] = [1, 0];
  const c: [number, number] = [1, 1];
  expect(buildGeometry("LineString", [a]).issue).toBe("incomplete");
  expect(buildGeometry("LineString", [a, b]).geometry).toEqual({
    type: "LineString",
    coordinates: [a, b],
  });
  expect(buildGeometry("Polygon", [a, b]).issue).toBe("incomplete");
  expect(buildGeometry("Polygon", [a, b, c]).geometry).toEqual({
    type: "Polygon",
    coordinates: [[a, b, c, a]],
  });
  expect(buildGeometry("MultiLineString", [a, b]).geometry).toEqual({
    type: "MultiLineString",
    coordinates: [[a, b]],
  });
  expect(buildGeometry("MultiPolygon", [a, b, c]).geometry).toEqual({
    type: "MultiPolygon",
    coordinates: [[[a, b, c, a]]],
  });
  expect(buildGeometry("LineString", []).issue).toBeNull();
});

test("pointsOf : relit ligne et polygone (sans le point de fermeture), refuse le multi-parties", () => {
  const a: [number, number] = [0, 0];
  const b: [number, number] = [1, 0];
  const c: [number, number] = [1, 1];
  expect(pointsOf({ type: "LineString", coordinates: [a, b] })).toEqual([a, b]);
  expect(pointsOf({ type: "Polygon", coordinates: [[a, b, c, a]] })).toEqual([a, b, c]);
  expect(pointsOf({ type: "MultiLineString", coordinates: [[a, b]] })).toEqual([a, b]);
  expect(
    pointsOf({
      type: "MultiLineString",
      coordinates: [
        [a, b],
        [b, c],
      ],
    }),
  ).toBeNull();
  expect(pointsOf(null)).toEqual([]);
});

test("distanceM : ~111 km par degré de latitude", () => {
  expect(Math.round(distanceM([0, 0], [0, 1]) / 1000)).toBe(111);
});

test("une ligne saisie point par point est envoyée en LineString", async () => {
  const c = renderForm("LineString");
  await addTyped("2", "48");
  await addTyped("2.1", "48.1");
  expect(screen.getByText("2 point(s) saisi(s)")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(c.createFeature).toHaveBeenCalled());
  expect(sent(c).geometry).toEqual({
    type: "LineString",
    coordinates: [
      [2, 48],
      [2.1, 48.1],
    ],
  });
});

test("un polygone est refermé et promu en MultiPolygon pour une collection Multi", async () => {
  const c = renderForm("MultiPolygon");
  await addTyped("0", "0");
  await addTyped("1", "0");
  await addTyped("1", "1");
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(c.createFeature).toHaveBeenCalled());
  expect(sent(c).geometry).toEqual({
    type: "MultiPolygon",
    coordinates: [
      [
        [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 0],
        ],
      ],
    ],
  });
});

test("une ligne incomplète bloque l'envoi avec un message", async () => {
  const c = renderForm("LineString");
  await addTyped("2", "48");
  expect(screen.getByRole("alert")).toHaveTextContent("au moins 2 points");
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(c.createFeature).not.toHaveBeenCalled();
});

test("une géométrie requise bloque l'envoi tant qu'elle est vide (ligne et point)", async () => {
  const line = renderForm("LineString", { required: true });
  await screen.findByRole("button", { name: "Envoyer" });
  await waitFor(() => expect(line.getCollectionSchema).toHaveBeenCalled());
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByText("La géométrie est obligatoire.")).toBeInTheDocument();
  expect(line.createFeature).not.toHaveBeenCalled();
});

test("point requis : message tant que lon/lat sont vides, envoi une fois saisis", async () => {
  const c = renderForm("Point", { required: true });
  await waitFor(() => expect(c.getCollectionSchema).toHaveBeenCalled());
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByText("La géométrie est obligatoire.")).toBeInTheDocument();
  expect(c.createFeature).not.toHaveBeenCalled();
  await userEvent.type(screen.getByLabelText("Longitude"), "2");
  await userEvent.type(screen.getByLabelText("Latitude"), "48");
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(c.createFeature).toHaveBeenCalled());
});

test("la trace GPS n'échantillonne qu'un point tous les 5 m au moins", async () => {
  let push: (p: unknown) => void = () => {};
  const clearWatch = vi.fn();
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: {
      watchPosition: (ok: (p: unknown) => void) => {
        push = ok;
        return 7;
      },
      clearWatch,
      getCurrentPosition: vi.fn(),
    },
  });
  const c = renderForm("LineString");
  await userEvent.click(screen.getByRole("button", { name: "Démarrer la trace GPS" }));
  const fix = (lat: number, accuracy = 4) =>
    act(() => push({ coords: { longitude: 2, latitude: lat, accuracy } }));
  fix(48);
  fix(48 + 0.00002); // ~2,2 m : ignoré
  fix(48 + 0.0001); // ~11 m : retenu
  fix(48 + 0.00012); // ~2 m du précédent : ignoré
  fix(48 + 0.0003); // retenu
  expect(screen.getByText(/3 point\(s\) saisi\(s\)/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Arrêter la trace GPS" }));
  expect(clearWatch).toHaveBeenCalledWith(7);
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(c.createFeature).toHaveBeenCalled());
  expect(sent(c).geometry.coordinates).toHaveLength(3);
});

test("une précision faible est signalée, une bonne est affichée sans alerte", async () => {
  let push: (p: unknown) => void = () => {};
  vi.stubGlobal("navigator", {
    ...navigator,
    geolocation: {
      watchPosition: (ok: (p: unknown) => void) => {
        push = ok;
        return 1;
      },
      clearWatch: vi.fn(),
      getCurrentPosition: vi.fn(),
    },
  });
  renderForm("LineString");
  await userEvent.click(screen.getByRole("button", { name: "Démarrer la trace GPS" }));
  act(() => push({ coords: { longitude: 2, latitude: 48, accuracy: 80 } }));
  expect(screen.getByText(/Précision faible : environ 80 m/)).toHaveAttribute("role", "alert");
  act(() => push({ coords: { longitude: 2, latitude: 48.01, accuracy: 6 } }));
  expect(screen.getByText("Précision : environ 6 m")).toBeInTheDocument();
});

test("gps_accuracy n'est envoyé que si la collection déclare la colonne", async () => {
  const getCurrentPosition = (ok: (p: unknown) => void) =>
    ok({ coords: { longitude: 2, latitude: 48, accuracy: 12.4 } });
  vi.stubGlobal("navigator", { ...navigator, geolocation: { getCurrentPosition } });
  const gps: FormField = {
    ...nom,
    name: "gps_accuracy",
    type: "number",
    label: "Précision GPS",
    order: 1,
  };
  const withCol = renderForm("Point", { mobile: true, extraFields: [gps] });
  await userEvent.click(screen.getByRole("button", { name: "Utiliser ma position" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(withCol.createFeature).toHaveBeenCalled());
  expect(sent(withCol).properties.gps_accuracy).toBe(12);
});

test("sans colonne gps_accuracy déclarée, la précision n'est pas envoyée", async () => {
  const getCurrentPosition = (ok: (p: unknown) => void) =>
    ok({ coords: { longitude: 2, latitude: 48, accuracy: 12.4 } });
  vi.stubGlobal("navigator", { ...navigator, geolocation: { getCurrentPosition } });
  const c = renderForm("Point", { mobile: true });
  await userEvent.click(screen.getByRole("button", { name: "Utiliser ma position" }));
  await userEvent.type(screen.getByLabelText("Nom"), "x");
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(c.createFeature).toHaveBeenCalled());
  expect(sent(c).properties).not.toHaveProperty("gps_accuracy");
});

// Chemin de lecture (piège n°5) : relire en édition un enregistrement ligne/polygone.
function renderEditable(geometryType: string, update = vi.fn().mockResolvedValue(undefined)) {
  const bus = new ActionBus();
  bus.configure([
    { id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" },
  ]);
  const client = {
    updateFeature: update,
    getCollectionPermission: vi.fn().mockResolvedValue(true),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds", fields: [nom], submitLabel: "Envoyer", geometryType }}
          ctx={
            {
              mode: "runtime",
              data: { loading: false, error: false, records: [], layer: "c" },
              bus,
              widgetId: "form1",
            } as WidgetContext
          }
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { bus, update };
}

test("loadRecord relit une ligne puis la renvoie telle quelle", async () => {
  const { bus, update } = renderEditable("LineString");
  act(() =>
    bus.emit("table1", "itemSelected", {
      id: 4,
      properties: { nom: "a" },
      geometry: {
        type: "LineString",
        coordinates: [
          [2, 48],
          [2.1, 48.1],
          [2.2, 48.2],
        ],
      },
    }),
  );
  expect(await screen.findByText("3 point(s) saisi(s)")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(update).toHaveBeenCalled());
  expect(update.mock.calls[0][2].geometry).toEqual({
    type: "LineString",
    coordinates: [
      [2, 48],
      [2.1, 48.1],
      [2.2, 48.2],
    ],
  });
});

test("loadRecord relit un polygone (sans point de fermeture) et une multi-parties est conservée", async () => {
  const { bus, update } = renderEditable("MultiLineString");
  const parts = [
    [
      [0, 0],
      [1, 1],
    ],
    [
      [5, 5],
      [6, 6],
    ],
  ];
  act(() =>
    bus.emit("table1", "itemSelected", {
      id: 5,
      properties: { nom: "b" },
      geometry: { type: "MultiLineString", coordinates: parts },
    }),
  );
  expect(await screen.findByText(/plusieurs parties/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(update).toHaveBeenCalled());
  expect(update.mock.calls[0][2].geometry).toEqual({ type: "MultiLineString", coordinates: parts });
});
