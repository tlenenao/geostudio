// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { registerDirectionsWidget } from "./directions";

beforeEach(() => {
  _resetRegistry();
  registerDirectionsWidget();
});

const ROUTE = {
  distance_km: 25.4,
  duration_s: 1800,
  geometry: { type: "LineString", coordinates: [[1.77, 45.26]] },
  legs: [
    {
      distance_km: 25.4,
      duration_s: 1800,
      maneuvers: [{ instruction: "Tournez à gauche.", distance_km: 1, duration_s: 60 }],
    },
  ],
};

function renderWidget(mode: WidgetContext["mode"], over: Partial<ItemClient> = {}) {
  const emit = vi.fn();
  const client = {
    geocode: vi.fn().mockResolvedValue([{ label: "Brive", lon: 1.53, lat: 45.16 }]),
    computeRoute: vi.fn().mockResolvedValue(ROUTE),
    ...over,
  };
  const Widget = getWidget("directions")!.Component;
  render(
    <ItemClientProvider client={client as unknown as ItemClient}>
      <Widget
        props={{}}
        ctx={{ mode, widgetId: "w1", bus: { emit } } as unknown as WidgetContext}
      />
    </ItemClientProvider>,
  );
  return { client, emit };
}

test("coordonnées + adresse : géocode seulement l'adresse, calcule puis émet routeComputed", async () => {
  const { client, emit } = renderWidget("runtime");
  fireEvent.change(screen.getByLabelText("Départ"), { target: { value: "45.26, 1.77" } });
  fireEvent.change(screen.getByLabelText("Arrivée"), { target: { value: "Brive" } });
  fireEvent.click(screen.getByRole("button", { name: "Calculer l'itinéraire" }));
  expect(await screen.findByText("25,4 km, 30 min.")).toBeInTheDocument();
  expect(screen.getByText("Tournez à gauche.")).toBeInTheDocument();
  expect(client.geocode).toHaveBeenCalledTimes(1);
  expect(client.computeRoute).toHaveBeenCalledWith(
    [
      { lon: 1.77, lat: 45.26 },
      { lon: 1.53, lat: 45.16 },
    ],
    "auto",
  );
  expect(emit).toHaveBeenCalledWith("w1", "routeComputed", {
    distanceKm: 25.4,
    durationS: 1800,
    geometry: ROUTE.geometry,
  });
});

test("adresse introuvable : message, aucun appel de routage", async () => {
  const { client } = renderWidget("runtime", { geocode: vi.fn().mockResolvedValue([]) });
  fireEvent.change(screen.getByLabelText("Départ"), { target: { value: "nulle part" } });
  fireEvent.change(screen.getByLabelText("Arrivée"), { target: { value: "45, 1" } });
  fireEvent.click(screen.getByRole("button", { name: "Calculer l'itinéraire" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Départ ou arrivée introuvable.");
  expect(client.computeRoute).not.toHaveBeenCalled();
});

test("service de routage absent : le message du cœur est affiché", async () => {
  renderWidget("runtime", {
    computeRoute: vi.fn().mockRejectedValue(new Error("Routage désactivé sur cette instance.")),
  });
  fireEvent.change(screen.getByLabelText("Départ"), { target: { value: "45, 1" } });
  fireEvent.change(screen.getByLabelText("Arrivée"), { target: { value: "46, 2" } });
  fireEvent.click(screen.getByRole("button", { name: "Calculer l'itinéraire" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Routage désactivé sur cette instance."),
  );
});

test("en édition : aucun appel réseau, simple repère", () => {
  const { client } = renderWidget("edit");
  expect(screen.getByText("Itinéraire (actif en aperçu et en exécution)")).toBeInTheDocument();
  expect(client.computeRoute).not.toHaveBeenCalled();
});
