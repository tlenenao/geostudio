// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../../api/ApiError";
import { QueryErrorState } from "./QueryErrorState";

const q = (error: unknown, refetch = vi.fn()) => ({ isError: true, error, refetch });

test("404 : message « introuvable » sans Réessayer", () => {
  render(<QueryErrorState queries={[q(new ApiError(404))]} notFoundMessage="Carte introuvable." />);
  expect(screen.getByRole("alert")).toHaveTextContent("Carte introuvable.");
  expect(screen.queryByRole("button", { name: "Réessayer" })).not.toBeInTheDocument();
});

test("403 : accès refusé", () => {
  render(<QueryErrorState queries={[q(new ApiError(403))]} notFoundMessage="Carte introuvable." />);
  expect(screen.getByRole("alert")).toHaveTextContent("Accès refusé.");
});

test("500 / réseau : erreur de chargement + Réessayer relance les requêtes en échec", async () => {
  const refetch = vi.fn();
  render(
    <QueryErrorState
      queries={[q(new ApiError(500), refetch), { isError: false, error: null, refetch: vi.fn() }]}
      notFoundMessage="Carte introuvable."
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Erreur de chargement.");
  await userEvent.click(screen.getByRole("button", { name: "Réessayer" }));
  expect(refetch).toHaveBeenCalledTimes(1);
});

test("aucune requête en erreur (donnée absente) : introuvable", () => {
  render(
    <QueryErrorState
      queries={[{ isError: false, error: null, refetch: vi.fn() }]}
      notFoundMessage="Carte introuvable."
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Carte introuvable.");
});
