// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { forwardRef, useImperativeHandle } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, MapConfig } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { ActionBus } from "../ActionBus";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { expectTokenizedClasses } from "../../ui/kit/testUtils";

const flyToSpy = vi.fn();
const configs: MapConfig[] = [];
const viewChanges: Array<((v: unknown) => void) | undefined> = [];

vi.mock("../../map/MapView", () => ({
  MapView: forwardRef(
    (
      { config, onViewChange }: { config: MapConfig; onViewChange?: (v: unknown) => void },
      ref: React.Ref<{ flyTo: unknown }>,
    ) => {
      configs.push(config);
      viewChanges.push(onViewChange);
      useImperativeHandle(ref, () => ({ flyTo: flyToSpy }));
      return <div data-testid="map-stub" />;
    },
  ),
}));

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
  configs.length = 0;
  viewChanges.length = 0;
  flyToSpy.mockReset();
});

test("galerie de fonds : radiogroup nommé, émet basemapChanged avec le style choisi", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("map1", "setBasemap", handler);
  bus.configure([
    { id: "m", from: "gal", event: "basemapChanged", to: "map1", action: "setBasemap" },
  ]);
  const Gallery = getWidget("basemapGallery")!.Component;
  const { container } = render(
    <Gallery
      props={{ title: "" }}
      ctx={{ mode: "runtime", bus, widgetId: "gal" } as WidgetContext}
    />,
  );
  expect(screen.getByRole("radiogroup", { name: "Fonds de carte" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("radio", { name: "Voyager" }));
  expect(handler).toHaveBeenCalledWith(
    expect.objectContaining({ style: expect.stringContaining("voyager") }),
  );
  expect(screen.getByRole("radio", { name: "Voyager" })).toHaveAttribute("aria-checked", "true");
  expectTokenizedClasses(container);
});

test("swipe : deux cartes, la droite porte les couches, la caméra de l'une suit l'autre", async () => {
  const client = { getAuthToken: () => undefined } as unknown as ItemClient;
  const Swipe = getWidget("swipe")!.Component;
  render(
    <ItemClientProvider client={client}>
      <Swipe
        props={{
          leftStyle: "https://a/style.json",
          rightStyle: "https://b/style.json",
          layers: [{ id: "l1", title: "L", visible: true, kind: "feature", url: "u" }],
        }}
        ctx={{ mode: "runtime" } as WidgetContext}
      />
    </ItemClientProvider>,
  );
  await waitFor(() => expect(screen.getAllByTestId("map-stub")).toHaveLength(2));
  const last = configs.slice(-2);
  expect(last[0].basemap.style).toBe("https://a/style.json");
  expect(last[0].layers).toHaveLength(0);
  expect(last[1].basemap.style).toBe("https://b/style.json");
  expect(last[1].layers).toHaveLength(1);
  const slider = screen.getByRole("slider", { name: "Position du comparateur" });
  fireEvent.change(slider, { target: { value: "30" } });
  expect(slider).toHaveValue("30");
  // La carte de gauche bouge : l'autre la suit, une seule fois (l'écho est ignoré).
  const view = { center: [3, 45], zoom: 7, pitch: 0, bearing: 0 };
  act(() => viewChanges[viewChanges.length - 2]?.(view));
  act(() => viewChanges[viewChanges.length - 1]?.(view));
  expect(flyToSpy).toHaveBeenCalledTimes(1);
});

function renderFiche(bus: ActionBus, props: Record<string, unknown>) {
  const client = {} as ItemClient;
  const qc = new QueryClient();
  const Fiche = getWidget("featureReport")!.Component;
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <Fiche props={props} ctx={{ mode: "preview", bus, widgetId: "fiche" } as WidgetContext} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("fiche d'entité : message vide puis fiche CEL après showRecord", () => {
  const bus = new ActionBus();
  renderFiche(bus, {
    titleTemplate: "Commune ${record.nom}",
    fields: [{ label: "Habitants", template: "${record.pop * 2}" }],
  });
  expect(screen.getByText(/Sélectionnez une entité/)).toBeInTheDocument();
  act(() => {
    bus.configure([
      { id: "m", from: "tbl", event: "itemSelected", to: "fiche", action: "showRecord" },
    ]);
    bus.emit("tbl", "itemSelected", { id: 7, properties: { nom: "Tulle", pop: 10 } });
  });
  expect(screen.getByRole("heading", { name: "Commune Tulle" })).toBeInTheDocument();
  expect(screen.getByText("Habitants")).toBeInTheDocument();
  expect(screen.getByText("20")).toBeInTheDocument();
});

test("fiche d'entité sans champs déclarés : liste toutes les propriétés", () => {
  const bus = new ActionBus();
  renderFiche(bus, {});
  act(() => {
    bus.configure([
      { id: "m", from: "tbl", event: "itemSelected", to: "fiche", action: "showRecord" },
    ]);
    bus.emit("tbl", "itemSelected", { id: 7, properties: { nom: "Tulle" } });
  });
  expect(screen.getByText("nom")).toBeInTheDocument();
  expect(screen.getByText("Tulle")).toBeInTheDocument();
});

test("PropsPanel des 3 widgets ARC-26 : chaque saisie remonte la config modifiée", () => {
  for (const [type, label, value, expected] of [
    ["basemapGallery", /Titre/, "Mes fonds", { title: "Mes fonds" }],
    ["featureReport", /Titre/, "Fiche", { titleTemplate: "Fiche" }],
  ] as const) {
    const onChange = vi.fn();
    const Panel = getWidget(type)!.PropsPanel!;
    const { unmount } = render(<Panel props={{}} onChange={onChange} dataSources={[]} />);
    fireEvent.change(screen.getAllByLabelText(label)[0], { target: { value } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining(expected));
    unmount();
  }
  const onChange = vi.fn();
  const Panel = getWidget("featureReport")!.PropsPanel!;
  const { container } = render(<Panel props={{}} onChange={onChange} dataSources={[]} />);
  fireEvent.change(container.querySelector("textarea")!, {
    target: { value: "Habitants = ${record.pop}\nsans égal" },
  });
  expect(onChange).toHaveBeenCalledWith({
    fields: [{ label: "Habitants", template: "${record.pop}" }],
  });
  const swipeChange = vi.fn();
  const SwipePanel = getWidget("swipe")!.PropsPanel!;
  const swipe = render(<SwipePanel props={{}} onChange={swipeChange} dataSources={[]} />);
  const sel = swipe.container.querySelectorAll("select")[1];
  fireEvent.change(sel, { target: { value: sel.querySelectorAll("option")[1].value } });
  expect(swipeChange).toHaveBeenCalledWith(
    expect.objectContaining({ rightStyle: sel.querySelectorAll("option")[1].value }),
  );
});

test("fiche d'entité en runtime : export PDF proposé quand l'export est activé et pk présent", async () => {
  const bus = new ActionBus();
  const client = {
    getInstanceInfo: async () => ({ exportEnabled: true }),
  } as unknown as ItemClient;
  const Fiche = getWidget("featureReport")!.Component;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/apps/app-1"]}>
          <Routes>
            <Route
              path="/apps/:pk"
              element={
                <Fiche
                  props={{}}
                  ctx={{ mode: "runtime", bus, widgetId: "fiche" } as WidgetContext}
                />
              }
            />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  act(() => {
    bus.configure([
      { id: "m", from: "tbl", event: "itemSelected", to: "fiche", action: "showRecord" },
    ]);
    bus.emit("tbl", "itemSelected", { id: 7, properties: { nom: "Tulle" } });
  });
  expect(await screen.findByRole("button", { name: /PDF|Exporter/i })).toBeInTheDocument();
});
