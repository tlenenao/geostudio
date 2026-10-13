// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { registerAnalysisWidget } from "./analysis";

beforeEach(() => {
  _resetRegistry();
  registerAnalysisWidget();
});

const TOOLS = [
  {
    name: "buffer",
    label: "Tampon",
    help: "Zone tampon autour des entités.",
    needsOtherCollection: false,
    paramsSchema: {
      properties: { distance: { type: "number", title: "Distance" } },
      required: ["distance"],
    },
  },
  {
    name: "intersection",
    label: "Intersection",
    help: "",
    needsOtherCollection: true,
    paramsSchema: { properties: {} },
  },
];

function renderWidget(mode: WidgetContext["mode"], over: Partial<ItemClient> = {}) {
  const client = {
    listAnalysisTools: vi.fn().mockResolvedValue(TOOLS),
    listCollections: vi.fn().mockResolvedValue([{ id: "c1", title: "Villes" }]),
    runAnalysis: vi.fn().mockResolvedValue({
      tool: "buffer",
      output: "ephemeral",
      srid: 4326,
      featureCollection: { type: "FeatureCollection", features: [{}, {}] },
    }),
    ...over,
  };
  const Widget = getWidget("analysis")!.Component;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={client as unknown as ItemClient}>
        <Widget props={{}} ctx={{ mode } as WidgetContext} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

test("exécute l'outil avec les paramètres typés puis affiche le décompte", async () => {
  const client = renderWidget("runtime");
  await screen.findByRole("option", { name: "Tampon" });
  fireEvent.change(screen.getByLabelText("Outil d'analyse"), { target: { value: "buffer" } });
  fireEvent.change(await screen.findByLabelText("Collection analysée"), {
    target: { value: "c1" },
  });
  fireEvent.change(screen.getByLabelText(/Distance/), { target: { value: "500" } });
  fireEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await screen.findByText(/2 entité\(s\) en résultat/);
  expect(client.runAnalysis).toHaveBeenCalledWith("c1", {
    tool: "buffer",
    params: { distance: 500 },
    otherCollectionId: undefined,
    output: "ephemeral",
    title: undefined,
  });
});

test("l'outil à deux jeux exige la seconde collection", async () => {
  renderWidget("runtime");
  await screen.findByRole("option", { name: "Intersection" });
  fireEvent.change(screen.getByLabelText("Outil d'analyse"), { target: { value: "intersection" } });
  fireEvent.change(await screen.findByLabelText("Collection analysée"), {
    target: { value: "c1" },
  });
  expect(screen.getByRole("button", { name: "Exécuter" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Seconde collection"), { target: { value: "c1" } });
  expect(screen.getByRole("button", { name: "Exécuter" })).toBeEnabled();
});

test("une erreur serveur est annoncée", async () => {
  renderWidget("runtime", { runAnalysis: vi.fn().mockRejectedValue(new Error("refusé")) });
  await screen.findByRole("option", { name: "Tampon" });
  fireEvent.change(screen.getByLabelText("Outil d'analyse"), { target: { value: "buffer" } });
  fireEvent.change(await screen.findByLabelText("Collection analysée"), {
    target: { value: "c1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("refusé"));
});

test("en mode edit : aucun appel réseau", () => {
  const client = renderWidget("edit");
  expect(client.listAnalysisTools).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("Outil d'analyse")).toBeNull();
});
