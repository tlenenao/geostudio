// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { BottomNav } from "./BottomNav";
import type { Profile } from "../../auth/capabilities";

const PROFILE: Profile = {
  isAdmin: true,
  isAnalyst: false,
  capabilities: {
    readOnly: false,
    etlEnabled: true,
    exportEnabled: false,
    appExportEnabled: false,
    tileset3dEnabled: false,
    terrain3dEnabled: false,
    copilotEnabled: false,
  },
};

test("affiche toujours les quatre entrées fixes", () => {
  render(
    <MemoryRouter>
      <BottomNav profile={PROFILE} />
    </MemoryRouter>,
  );
  for (const label of ["Catalogue", "Cartes", "Tâches", "Plus"]) {
    expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
  }
});

test("Plus ouvre les domaines restants accessibles au profil", async () => {
  render(
    <MemoryRouter>
      <BottomNav profile={PROFILE} />
    </MemoryRouter>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Plus" }));
  expect(screen.getByRole("link", { name: "Administration" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Données" })).toBeInTheDocument();
});

test("marque l'entrée fixe active via aria-current, y compris sur une route en ?type=", () => {
  render(
    <MemoryRouter initialEntries={["/?type=map"]}>
      <BottomNav profile={PROFILE} />
    </MemoryRouter>,
  );
  const cartes = screen.getByRole("button", { name: "Cartes" });
  const catalogue = screen.getByRole("button", { name: "Catalogue" });
  const taches = screen.getByRole("button", { name: "Tâches" });
  expect(cartes).toHaveAttribute("aria-current", "page");
  expect(catalogue).not.toHaveAttribute("aria-current");
  expect(taches).not.toHaveAttribute("aria-current");
});
