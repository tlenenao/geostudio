// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { registerAddressSearchWidget } from "./addressSearch";

beforeEach(() => {
  _resetRegistry();
  registerAddressSearchWidget();
});

function renderWidget(mode: WidgetContext["mode"], geocode = vi.fn()) {
  const emit = vi.fn();
  const Widget = getWidget("addressSearch")!.Component;
  render(
    <ItemClientProvider client={{ geocode } as unknown as ItemClient}>
      <Widget
        props={{}}
        ctx={{ mode, widgetId: "addr1", bus: { emit } } as unknown as WidgetContext}
      />
    </ItemClientProvider>,
  );
  return { emit, geocode };
}

test("enregistré avec l'événement addressSelected", () => {
  expect(getWidget("addressSearch")!.events).toEqual(["addressSelected"]);
});

test("la sélection d'un résultat émet {center:[lon,lat]}", async () => {
  const { emit } = renderWidget(
    "runtime",
    vi.fn().mockResolvedValue([{ label: "Tulle", lon: 1.77, lat: 45.26 }]),
  );
  fireEvent.change(await screen.findByLabelText("Rechercher une adresse"), {
    target: { value: "tulle" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Localiser" }));
  fireEvent.click(await screen.findByRole("button", { name: "Tulle" }));
  await waitFor(() =>
    expect(emit).toHaveBeenCalledWith("addr1", "addressSelected", { center: [1.77, 45.26] }),
  );
});

test("en mode edit : aucun champ ni appel réseau", () => {
  const { geocode } = renderWidget("edit");
  expect(screen.queryByLabelText("Rechercher une adresse")).toBeNull();
  expect(geocode).not.toHaveBeenCalled();
});
