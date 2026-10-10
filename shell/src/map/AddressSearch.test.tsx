// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";
import { createGeocodingMethods } from "../api/domains/geocoding";
import { expectTokenizedClasses } from "../ui/kit/testUtils";
import { AddressSearch } from "./AddressSearch";

function renderWith(geocode: ReturnType<typeof vi.fn>, onSelect = vi.fn()) {
  const view = render(
    <ItemClientProvider client={{ geocode } as unknown as ItemClient}>
      <AddressSearch onSelect={onSelect} />
    </ItemClientProvider>,
  );
  return { onSelect, container: view.container };
}

describe("AddressSearch", () => {
  it("searches on submit only and flies to the chosen result", async () => {
    const geocode = vi
      .fn()
      .mockResolvedValue([{ label: "1 Rue de Pontoise 95000 Cergy", lon: 2.0628, lat: 49.0316 }]);
    const { onSelect } = renderWith(geocode);
    await userEvent.type(screen.getByLabelText("Rechercher une adresse"), "1 rue de pontoise");
    expect(geocode).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Localiser" }));
    expect(geocode).toHaveBeenCalledWith("1 rue de pontoise");
    expect(onSelect).not.toHaveBeenCalled();
    await userEvent.click(
      await screen.findByRole("button", { name: "1 Rue de Pontoise 95000 Cergy" }),
    );
    expect(onSelect).toHaveBeenCalledWith([2.0628, 49.0316]);
  });

  it("disables the search below 3 characters", async () => {
    renderWith(vi.fn());
    await userEvent.type(screen.getByLabelText("Rechercher une adresse"), "ab");
    expect(screen.getByRole("button", { name: "Localiser" })).toBeDisabled();
  });

  it("says when nothing matches and when the service fails", async () => {
    const geocode = vi.fn().mockResolvedValueOnce([]).mockRejectedValueOnce(new Error("502"));
    const { container } = renderWith(geocode);
    await userEvent.type(screen.getByLabelText("Rechercher une adresse"), "nulle part");
    await userEvent.click(screen.getByRole("button", { name: "Localiser" }));
    expect(await screen.findByText("Aucune adresse trouvée.")).toHaveAttribute("role", "status");
    await userEvent.click(screen.getByRole("button", { name: "Localiser" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Recherche d'adresse indisponible.");
    expectTokenizedClasses(container);
  });
});

describe("createGeocodingMethods", () => {
  it("calls GET /geocode with an encoded query and unwraps results", async () => {
    const request = vi.fn().mockResolvedValue({ results: [{ label: "A", lon: 1, lat: 2 }] });
    const methods = createGeocodingMethods({ request } as never);
    await expect(methods.geocode("1 rue & co")).resolves.toEqual([{ label: "A", lon: 1, lat: 2 }]);
    expect(request).toHaveBeenCalledWith("GET", "/geocode?q=1+rue+%26+co&limit=5");
  });
});
