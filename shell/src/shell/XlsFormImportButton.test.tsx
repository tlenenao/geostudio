// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ApiError } from "../api/ApiError";
import type { ItemClient } from "../api/types";
import { XlsFormImportButton } from "./XlsFormImportButton";

function setup(importXlsForm: ItemClient["importXlsForm"]) {
  const client = {
    importXlsForm,
    getMe: vi.fn().mockResolvedValue({ privileges: ["data.manage"] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <MemoryRouter>
          <XlsFormImportButton />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

const file = () =>
  new File(["x"], "f.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

test("importe un fichier et affiche le rapport des éléments non portés", async () => {
  setup(
    vi.fn().mockResolvedValue({
      collectionId: "c1",
      itemId: "i1",
      title: "Enquête",
      report: [
        { code: "approximated", message: "select_multiple stocké en texte", row: 4, name: "q" },
      ],
    }),
  );
  await userEvent.click(await screen.findByRole("button", { name: "Importer un XLSForm" }));
  await userEvent.upload(screen.getByLabelText("Fichier XLSForm"), file());
  expect(await screen.findByText(/Formulaire « Enquête » importé/)).toBeInTheDocument();
  expect(screen.getByText(/ligne 4 : select_multiple/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Ouvrir l'application de collecte" })).toHaveAttribute(
    "href",
    "/apps/i1/edit",
  );
});

test("un rapport vide dit que tout est porté", async () => {
  setup(vi.fn().mockResolvedValue({ collectionId: "c", itemId: "i", title: "T", report: [] }));
  await userEvent.click(await screen.findByRole("button", { name: "Importer un XLSForm" }));
  await userEvent.upload(screen.getByLabelText("Fichier XLSForm"), file());
  expect(await screen.findByText("Tout le formulaire a été porté sans perte.")).toBeInTheDocument();
});

test("une erreur du cœur est affichée avec son detail", async () => {
  setup(vi.fn().mockRejectedValue(new ApiError(400, { title: "x", detail: "Fichier illisible." })));
  await userEvent.click(await screen.findByRole("button", { name: "Importer un XLSForm" }));
  await userEvent.upload(screen.getByLabelText("Fichier XLSForm"), file());
  expect(await screen.findByRole("alert")).toHaveTextContent("Fichier illisible.");
});
